"""Slack Assistant surface adapter for the Data Assistant.

This module is the thin Slack edge between Slack's Bolt ``Assistant`` container
and the core Data Assistant workflow (interpret -> route -> authorize -> prepare
-> reason -> compose). It replaces the classic-bot DM boundary (see ADR-0015).

The adapter is split in two:

* ``AssistantAdapter`` -- a frozen, pure dataclass with two handler methods
  (``on_thread_started``, ``on_user_message``). It receives Slack's transient
  utilities (``say``, ``set_status``, ``set_suggested_prompts``) as injected
  callables, so it is fully testable with fakes and never touches a live API.
* ``register_assistant_handlers`` -- a thin Bolt wiring shim that builds a Bolt
  ``Assistant``, registers two listeners that forward to the adapter, and mounts
  it on the app via ``app.use(assistant)``. The shim is intentionally untested:
  the adapter carries the behavior.

The interpret->compose pipeline, its evals, and the Non-Answer path are
UNCHANGED -- divergence is contained to this Slack edge.
"""

from __future__ import annotations

import collections.abc as collections_abc
import contextlib
import dataclasses
import datetime
import logging
import pathlib
import time
import typing
import uuid

import duckdb
import pandas as pd

import data_assistant.access_controller as access_controller
import data_assistant.interaction_log as interaction_log
import data_assistant.workflow.contracts as contracts

logger = logging.getLogger(__name__)

GREETING = (
    "Hi! I answer questions about the retail operations data — orders, products, "
    "customers, stores, support, inventory. Pick a prompt below or ask your own. "
    "I'll only answer what the data supports."
)

# Provisional — rehearsed set locked in #101. Delivered dynamically via
# set_suggested_prompts (NOT manifest static). All three are summarize-intent and
# answerable today; deliberately no top-N "which ... highest" (that is #102).
SUGGESTED_PROMPTS: tuple[dict[str, str], ...] = (
    {
        "title": "Revenue by region",
        "message": "What was total net revenue by store region in Q1 2026?",
    },
    {
        "title": "Customers by loyalty tier",
        "message": "What was customer count by loyalty tier for all time?",
    },
    {
        "title": "Tickets by issue category",
        "message": "What was support ticket count by issue category in April 2026?",
    },
)

# --- Flag buttons (issue #111) ----------------------------------------------
# Every Assistant reply carries two flag buttons so a maintainer can mark a bad
# response in place; a click flags the Interaction Log record (by id), which the
# maintainer later pastes into Claude Code ("look at the flagged correctness
# cases"). The action_id -> category map is the SINGLE source of truth shared by
# the button-builder and the block_actions handler; categories are exactly the
# interaction_log.FLAG_VOCABULARY.
FLAG_CORRECTNESS_ACTION_ID: typing.Final[str] = "flag_correctness"
FLAG_FORMATTING_ACTION_ID: typing.Final[str] = "flag_formatting"

ACTION_ID_TO_CATEGORY: typing.Final[dict[str, str]] = {
    FLAG_CORRECTNESS_ACTION_ID: "correctness",
    FLAG_FORMATTING_ACTION_ID: "formatting",
}

# Seam types for the pure block_actions core. ``FlagStore`` binds to
# ``interaction_log.flag_interaction(.., path=log_path)`` (returns False on an
# unknown id); ``Confirm`` posts the ephemeral confirmation text.
FlagStore: typing.TypeAlias = collections_abc.Callable[[str, str], bool]
Confirm: typing.TypeAlias = collections_abc.Callable[[str], None]


def flag_action_blocks(interaction_id: str) -> tuple[contracts.SlackBlock, ...]:
    """Build the Slack ``actions`` block with the two flag buttons.

    Each button carries ``interaction_id`` in its ``value`` so the
    ``block_actions`` handler can flag the right Interaction Log record. The
    block_id also carries the id for good measure. This is a pure, static
    blocks tuple -- it never touches the run trace, so it cannot resurrect the
    record-build masking bug.
    """
    return (
        {
            "type": "actions",
            "block_id": f"flag_actions:{interaction_id}",
            "elements": [
                {
                    "type": "button",
                    "action_id": FLAG_CORRECTNESS_ACTION_ID,
                    "text": {"type": "plain_text", "text": "🚩 Incorrect"},
                    "value": interaction_id,
                },
                {
                    "type": "button",
                    "action_id": FLAG_FORMATTING_ACTION_ID,
                    "text": {"type": "plain_text", "text": "🎨 Formatting"},
                    "value": interaction_id,
                },
            ],
        },
    )


def apply_flag(
    *,
    action_id: str,
    interaction_id: str,
    flag_store: FlagStore,
    confirm: Confirm,
) -> None:
    """Pure block_actions core: flag the record, then confirm ephemerally.

    Maps ``action_id`` to its flag category, calls ``flag_store`` to persist the
    flag, and posts a confirmation via ``confirm``. An unmapped ``action_id`` is
    a defensive no-op (never flags, never crashes). When ``flag_store`` reports
    the id was not found (``False``) we confirm a benign "couldn't find that
    interaction" message instead of the success text -- a crash is never the
    right response to a stray button click.
    """
    category = ACTION_ID_TO_CATEGORY.get(action_id)
    if category is None:
        return
    found = flag_store(interaction_id, category)
    if found:
        confirm(f"Flagged: {category} ✓")
    else:
        confirm("Sorry, I couldn't find that interaction to flag.")


RUNTIME_FALLBACK_MESSAGE = (
    "Something went wrong while answering your question. Please try again in a bit."
)
"""Adapter-level last-resort reply posted when an unexpected exception crashes
the answer path. This is a Runtime Fallback Message, NOT a Non-Answer Response:
it never routes through the Non-Answer Catalog and carries no reason or next
step. The Assistant transient status auto-clears when this reply is sent, so no
manual status clear is needed."""


SlackWorkflowResult: typing.TypeAlias = contracts.WorkflowResult

AnswerPath: typing.TypeAlias = collections_abc.Callable[
    [
        duckdb.DuckDBPyConnection,
        str,
        contracts.InternalIdentity,
        contracts.ProgressSink,
    ],
    SlackWorkflowResult,
]

ConnectionFactory: typing.TypeAlias = collections_abc.Callable[
    [], contextlib.AbstractContextManager[duckdb.DuckDBPyConnection]
]

AssistantIdentityResolver: typing.TypeAlias = collections_abc.Callable[
    [str], contracts.InternalIdentity
]


class StatusSetter(typing.Protocol):
    """Injected Slack ``set_status`` callable (transient assistant status)."""

    def __call__(self, status: str) -> None:
        """Set the transient assistant status for the current thread."""


class Sayer(typing.Protocol):
    """Injected Slack ``say`` callable (posts a threaded assistant reply)."""

    def __call__(
        self,
        text: str,
        *,
        blocks: collections_abc.Sequence[contracts.SlackBlock] | None = None,
    ) -> None:
        """Post a reply into the assistant thread."""


class SuggestedPromptsSetter(typing.Protocol):
    """Injected Slack ``set_suggested_prompts`` callable."""

    def __call__(self, *, prompts: list[dict[str, str]]) -> None:
        """Offer suggested prompts in the assistant thread."""


def default_identity(user: str) -> contracts.InternalIdentity:
    """Map a Slack user id into the workflow contract without org policy."""
    return contracts.InternalIdentity(identity_id=f"slack_user:{user}")


def dev_identity(user: str) -> contracts.InternalIdentity:
    """Use the local allowed identity for manual development smoke testing."""
    del user
    return access_controller.DEFAULT_LOCAL_ALLOWED_IDENTITY


def final_response_from_workflow_result(
    result: SlackWorkflowResult,
) -> contracts.FinalResponse:
    """Return the core workflow result's user-facing Final Response.

    Renders both real answers and Non-Answers to a ``FinalResponse`` (text +
    Trust-Summary blocks); the adapter just ``say``s whatever this returns.
    """
    if isinstance(result, contracts.FinalResponse):
        return result
    return result.final_response


def _latency_ms(started_at: float) -> int:
    return int((time.monotonic() - started_at) * 1000)


def _interaction_record(
    *,
    interaction_id: str,
    timestamp: str,
    latency_ms: int,
    user: str,
    question: str,
    model: str,
    result: SlackWorkflowResult,
) -> dict[str, object]:
    """Build the sanitized Interaction Log record for a successful run.

    SUCCESS branches on the result type (ADR-0016): a ``DataAssistantRun`` is an
    answer; a bare ``FinalResponse`` is a Non-Answer. Either way the record
    carries the always-fields plus outcome-specific detail. It NEVER carries raw
    Prepared Data cell values (see ``_answer_fields``).
    """
    final_response = final_response_from_workflow_result(result)
    record: dict[str, object] = {
        "id": interaction_id,
        "timestamp": timestamp,
        "user": user,
        "question": question,
        "latency_ms": latency_ms,
        "response_text": final_response.text,
        "model": model,
        "flags": [],
    }
    if isinstance(result, contracts.DataAssistantRun):
        record["outcome"] = "answer"
        record.update(_answer_fields(result))
    else:
        record["outcome"] = "non_answer"
        record.update(_non_answer_fields(final_response.non_answer))
    return record


def _error_record(
    *,
    interaction_id: str,
    timestamp: str,
    latency_ms: int,
    user: str,
    question: str,
    model: str,
    error: BaseException,
) -> dict[str, object]:
    """Build the Interaction Log record for a crashed answer path."""
    return {
        "id": interaction_id,
        "timestamp": timestamp,
        "user": user,
        "question": question,
        "latency_ms": latency_ms,
        "response_text": RUNTIME_FALLBACK_MESSAGE,
        "model": model,
        "flags": [],
        "outcome": "error",
        "error_type": type(error).__name__,
        "error_message": str(error),
    }


def _answer_fields(run: contracts.DataAssistantRun) -> dict[str, object]:
    """Sanitized answer-specific fields from a successful run trace.

    Includes the Question Frame summary, the routed Data Request, the
    prepared-data SHAPE (rows x columns) + quality notes, and the tiny
    ``key_data`` headline numbers -- the ONE deliberate inclusion of cell values
    (ADR-0016). Bulk Prepared Data cell values are excluded by design.
    """
    data_request = run.data_request
    prepared = run.prepared_data
    rows, columns = prepared.data.shape
    return {
        "intent": run.question_frame.intent,
        "question_frame": _question_frame_summary(run.question_frame),
        "dataset": data_request.dataset.name,
        "metric": data_request.metric.label,
        "metric_expression": data_request.metric.expression,
        "group_by": [field.label for field in data_request.group_by_fields],
        "filters": list(data_request.filter_labels),
        "result_limit": data_request.result_limit,
        "prepared_data_shape": {"rows": int(rows), "columns": int(columns)},
        "quality_notes": list(prepared.quality_notes),
        "key_data": _key_data_records(run.answer_draft.key_data),
    }


def _non_answer_fields(non_answer: contracts.NonAnswer | None) -> dict[str, object]:
    """Non-Answer-specific fields read from FinalResponse.non_answer."""
    if non_answer is None:
        return {}
    return {
        "stage": str(non_answer.stage),
        "reason_code": str(non_answer.reason_code),
        "context": list(non_answer.context),
    }


def _question_frame_summary(
    question_frame: contracts.QuestionFrame,
) -> dict[str, object]:
    return {
        "intent": question_frame.intent,
        "metric": question_frame.metric,
        "time_scope": str(question_frame.time_scope),
        "filters": list(question_frame.filter_labels),
        "unresolved_ambiguities": list(question_frame.unresolved_ambiguities),
    }


def _key_data_records(key_data: pd.DataFrame) -> list[dict[str, object]]:
    """Serialize the small ``key_data`` headline frame to JSON-safe records.

    ``key_data`` is a tiny ``pd.DataFrame`` (the headline rows). We turn it into
    a list of ``{column: value}`` dicts, coercing each value to a JSON-safe
    scalar so the line is greppable and never carries pandas/NumPy types. This
    is the deliberate, documented inclusion of cell values (ADR-0016); the bulk
    Prepared Data frame is never serialized.
    """
    records: list[dict[typing.Hashable, object]] = key_data.to_dict(orient="records")
    return [
        {str(column): _json_safe(value) for column, value in record.items()}
        for record in records
    ]


def _json_safe(value: object) -> object:
    if isinstance(value, bool | int | float | str) or value is None:
        return value
    return str(value)


@dataclasses.dataclass(frozen=True)
class AssistantAdapter:
    """Pure adapter from Slack Assistant events to the Data Assistant workflow."""

    connection_factory: ConnectionFactory
    answer_path: AnswerPath
    internal_identity_resolver: AssistantIdentityResolver = default_identity
    # Model label recorded on every Interaction Log line (ADR-0016). Threaded
    # from slack_runtime.py where the OpenAI model is configured; empty by
    # default so the adapter stays test-constructible without live config.
    model_label: str = ""
    # Injectable so tests write to tmp_path and never touch the real gitignored
    # logs/interactions.jsonl.
    log_path: pathlib.Path = interaction_log.DEFAULT_LOG_PATH

    def on_thread_started(
        self,
        *,
        say: Sayer,
        set_suggested_prompts: SuggestedPromptsSetter,
    ) -> None:
        """Greet the user and offer the provisional suggested prompts."""
        say(GREETING)
        set_suggested_prompts(prompts=[dict(prompt) for prompt in SUGGESTED_PROMPTS])

    def on_user_message(
        self,
        *,
        text: str,
        user: str,
        channel: str,
        thread_ts: str,
        set_status: StatusSetter,
        say: Sayer,
    ) -> None:
        """Run the pipeline for one user message and reply in the thread.

        ``channel`` and ``thread_ts`` are used only for the maintainer log line;
        ``say`` and ``set_status`` are already bound to the thread by Bolt. The
        transient status auto-clears when ``say`` posts the reply (both the
        success and the fallback path), so there is no manual status clear.
        """
        internal_identity = self.internal_identity_resolver(user)
        interaction_id = uuid.uuid4().hex
        started_at = time.monotonic()
        timestamp = datetime.datetime.now(datetime.UTC).isoformat()
        try:
            with self.connection_factory() as connection:
                result = self.answer_path(
                    connection,
                    text,
                    internal_identity,
                    set_status,
                )
            final_response = final_response_from_workflow_result(result)
            self._record_interaction(
                lambda: _interaction_record(
                    interaction_id=interaction_id,
                    timestamp=timestamp,
                    latency_ms=_latency_ms(started_at),
                    user=user,
                    question=text,
                    model=self.model_label,
                    result=result,
                ),
            )
            reply_blocks = tuple(final_response.blocks) + flag_action_blocks(
                interaction_id
            )
            say(final_response.text, blocks=reply_blocks)
        except Exception as error:
            # Bind to a stable local: `except ... as error` clears `error` at
            # the end of the block, so the record-building thunk closes over
            # this name instead (the thunk runs synchronously, but this also
            # keeps it lexically valid).
            caught = error
            # Bootcamp deviation: we also log the raw question text (`text`).
            # A real production Slack bot would NOT log the question text because
            # it is user-provided free text that may contain sensitive or
            # business values (see CONTEXT.md: "Log the Decision Trail, not raw
            # Prepared Data or sensitive values"). The stack trace stays in logs
            # only and never reaches the Slack user.
            logger.exception(
                "Slack Assistant Adapter failed to answer "
                "(channel=%s thread_ts=%s user=%s exception_type=%s question=%s)",
                channel,
                thread_ts,
                user,
                type(caught).__name__,
                text,
            )
            # Append the error record before the fallback say. Building and
            # appending are both wrapped so a logging failure can never block
            # the user reply.
            self._record_interaction(
                lambda: _error_record(
                    interaction_id=interaction_id,
                    timestamp=timestamp,
                    latency_ms=_latency_ms(started_at),
                    user=user,
                    question=text,
                    model=self.model_label,
                    error=caught,
                ),
            )
            # Log first, then deliver the Runtime Fallback Message. If this `say`
            # itself raises we let it propagate: the maintainer log already
            # exists. The fallback is NOT a Non-Answer. It still carries the flag
            # buttons (its error record exists) so a crash reply is flaggable.
            fallback_section: contracts.SlackBlock = {
                "type": "section",
                "text": {"type": "mrkdwn", "text": RUNTIME_FALLBACK_MESSAGE},
            }
            fallback_blocks = (fallback_section,) + flag_action_blocks(interaction_id)
            say(RUNTIME_FALLBACK_MESSAGE, blocks=fallback_blocks)

    def _record_interaction(
        self,
        build_record: collections_abc.Callable[[], dict[str, object]],
    ) -> None:
        """Build then append one Interaction Log line; never break the reply.

        The user-facing ``say`` is more important than the log line, so the
        swallow covers BOTH record CONSTRUCTION (``to_dict`` / ``.shape`` / field
        extraction on the trace, via the ``build_record`` thunk) AND the append.
        Any failure in either is logged and dropped here rather than propagated
        into the caller's ``except``, which would suppress a good answer.
        """
        try:
            record = build_record()
            interaction_log.append_interaction(record, path=self.log_path)
        except Exception:
            logger.exception("Failed to record Interaction Log entry.")


def register_assistant_handlers(
    *,
    app: typing.Any,
    adapter: AssistantAdapter,
) -> None:
    """Wire the adapter into a Bolt ``Assistant`` container (thin shim).

    This is the only live-API-shaped code in the module and is intentionally
    untested: it forwards Bolt's injected utilities to the pure adapter. Bolt
    injects listener arguments by exact name (verified against slack_bolt
    1.28.0): ``say``, ``set_status``, ``set_suggested_prompts``, ``context``.
    ``context.user_id`` / ``context.channel_id`` / ``context.thread_ts`` carry
    the routing identifiers.
    """
    from slack_bolt import Assistant

    # Typed as Any: Bolt's decorator signatures are loosely typed and would
    # otherwise leak "partially unknown" through this shim.
    assistant: typing.Any = Assistant()

    def _thread_started(
        say: Sayer,
        set_suggested_prompts: SuggestedPromptsSetter,
    ) -> None:
        adapter.on_thread_started(
            say=say,
            set_suggested_prompts=set_suggested_prompts,
        )

    def _user_message(
        payload: dict[str, typing.Any],
        context: typing.Any,
        set_status: StatusSetter,
        say: Sayer,
    ) -> None:
        adapter.on_user_message(
            text=payload.get("text", ""),
            user=context.user_id or "",
            channel=context.channel_id or "",
            thread_ts=context.thread_ts or "",
            set_status=set_status,
            say=say,
        )

    # Bolt injects listener arguments by exact name (verified against slack_bolt
    # 1.28.0 kwargs injection): thread_started gets `say`/`set_suggested_prompts`;
    # user_message gets `payload`/`context`/`set_status`/`say`.
    assistant.thread_started(_thread_started)
    assistant.user_message(_user_message)

    # assistant_thread_context_changed is intentionally NOT handled: we rely on
    # Bolt's default in-memory thread-context store. This is deliberate, not an
    # oversight.

    app.use(assistant)

    _register_flag_actions(app=app, adapter=adapter)


def _register_flag_actions(
    *,
    app: typing.Any,
    adapter: AssistantAdapter,
) -> None:
    """Wire the flag buttons' ``block_actions`` listeners (thin untested shim).

    For each flag ``action_id`` we register a Bolt action listener that, over
    Socket Mode: ``ack()``s first, reads the embedded ``interaction_id`` from
    the button ``value`` in ``body``, binds the ``flag_store`` seam to
    ``interaction_log.flag_interaction`` (with the adapter's ``log_path``) and
    the ``confirm`` seam to an ephemeral ``respond``, then delegates to the pure
    ``apply_flag``. All behavior lives in ``apply_flag``; this shim is the only
    live-API-shaped code here and is intentionally untested.

    Bolt's ``respond`` is bound to the action's ``response_url``; calling
    ``respond(text=..., response_type="ephemeral", replace_original=False)``
    posts a SEPARATE ephemeral message visible only to the clicking maintainer
    and LEAVES THE ORIGINAL ANSWER in place. ``replace_original=False`` is
    load-bearing: omitting it makes Slack replace the answer message the buttons
    are attached to (verified against the ``slack_bolt`` 1.28.0
    ``Respond.__call__`` signature: ``text`` then keyword ``response_type`` /
    ``replace_original``).
    """

    def _flag_action(
        ack: collections_abc.Callable[[], None],
        body: dict[str, typing.Any],
        respond: typing.Any,
    ) -> None:
        ack()
        actions: list[dict[str, typing.Any]] = body.get("actions") or [{}]
        action = actions[0]
        action_id = str(action.get("action_id", ""))
        interaction_id = str(action.get("value", ""))

        def flag_store(target_id: str, category: str) -> bool:
            return interaction_log.flag_interaction(
                target_id, category, path=adapter.log_path
            )

        def confirm(text: str) -> None:
            # replace_original=False is REQUIRED: for block_actions, omitting it
            # makes Slack REPLACE the original message (the answer the buttons
            # are attached to) with this confirmation. We want the answer to
            # stay; post the confirmation as a separate ephemeral message.
            respond(
                text=text,
                response_type="ephemeral",
                replace_original=False,
            )

        apply_flag(
            action_id=action_id,
            interaction_id=interaction_id,
            flag_store=flag_store,
            confirm=confirm,
        )

    # Register one listener per flag action_id (the single source of truth).
    for flag_action_id in ACTION_ID_TO_CATEGORY:
        app.action(flag_action_id)(_flag_action)

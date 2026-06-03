"""The pure Slack Assistant adapter and its contracts.

``AssistantAdapter`` is a frozen, pure dataclass with handler methods that
receive Slack's transient utilities (``say``, ``set_status``,
``set_suggested_prompts``) as injected callables, so it is fully testable with
fakes and never touches a live API. The Bolt wiring that supplies those
callables lives in ``wiring``; the block construction it renders lives in
``blocks``. The interpret->compose pipeline, its evals, and the Non-Answer path
are UNCHANGED -- divergence is contained to this Slack edge (ADR-0015).
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

import data_assistant.access_controller as access_controller
import data_assistant.assistant_thread_pointer as assistant_thread_pointer
import data_assistant.interaction_log as interaction_log
import data_assistant.interaction_record as interaction_record
import data_assistant.workflow.contracts as contracts
from data_assistant.interaction_record import (
    RUNTIME_FALLBACK_MESSAGE,
    QAReviewContext,
    final_response_from_workflow_result,
)
from data_assistant.slack.blocks import (
    build_runtime_fallback_blocks,
    visible_response_blocks,
)
from data_assistant.slack.blocks import (
    reply_blocks as build_reply_blocks,
)
from data_assistant.slack.prompts import GREETING, SUGGESTED_PROMPTS

logger = logging.getLogger(__name__)

# ``RUNTIME_FALLBACK_MESSAGE``, ``QAReviewContext`` and
# ``final_response_from_workflow_result`` are imported above from
# ``interaction_record`` (their natural owner -- it reads the workflow result and
# writes the canonical fallback ``response_text``). They are re-exported here so
# this edge's block/adapter sites and ``slack_qa.driver`` keep using them.
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


def _latency_ms(started_at: float) -> int:
    return int((time.monotonic() - started_at) * 1000)


@dataclasses.dataclass(frozen=True)
class AssistantAdapter:
    """Pure adapter from Slack Assistant events to the Data Assistant workflow."""

    connection_factory: ConnectionFactory
    answer_path: AnswerPath
    internal_identity_resolver: AssistantIdentityResolver = default_identity
    # Model label recorded on every Interaction Log line (ADR-0016). Threaded
    # from slack/runtime_main.py where the OpenAI model is configured; empty by
    # default so the adapter stays test-constructible without live config.
    model_label: str = ""
    # Injectable so tests write to tmp_path and never touch the real gitignored
    # logs/interactions.jsonl.
    log_path: pathlib.Path = interaction_log.DEFAULT_LOG_PATH
    # Injectable last-opened-thread pointer (issue #128): on_thread_started
    # records (channel, thread_ts) here so the QA driver can auto-discover the
    # most recently opened assistant thread. Same tmp_path injection as log_path.
    pointer_path: pathlib.Path = assistant_thread_pointer.DEFAULT_POINTER_PATH

    def on_thread_started(
        self,
        *,
        say: Sayer,
        set_suggested_prompts: SuggestedPromptsSetter,
        channel: str,
        thread_ts: str,
    ) -> None:
        """Greet the user, offer prompts, and record the thread pointer.

        Writing the (channel, thread_ts) pointer is best-effort discovery state
        for the QA driver; it is wrapped so a write failure NEVER blocks the
        greeting or suggested prompts -- the same 'reply/greeting wins' boundary
        as the Interaction Log capture.
        """
        say(GREETING)
        set_suggested_prompts(prompts=[dict(prompt) for prompt in SUGGESTED_PROMPTS])
        try:
            assistant_thread_pointer.write_latest(
                channel,
                thread_ts,
                path=self.pointer_path,
            )
        except Exception:
            logger.exception("Failed to record assistant-thread pointer.")

    def answer_and_render(
        self,
        *,
        text: str,
        user: str,
        qa_case_id: str | None = None,
        qa_review_context: QAReviewContext | None = None,
        set_status: StatusSetter,
    ) -> tuple[str, contracts.FinalResponse, tuple[contracts.SlackBlock, ...]]:
        """Run the success core for one question and return it ready to post.

        This is the shared ``id -> answer -> log -> render-with-buttons`` core
        extracted from :meth:`on_user_message` so both the Slack adapter and the
        manual QA driver (issue #128) run the SAME path -- the driver never
        drifts from the real adapter. It:

        * mints a fresh ``interaction_id`` and starts the latency clock,
        * opens the data connection and runs the injected ``answer_path``
          (progress flows through ``set_status``),
        * append-first records the sanitized Interaction Log line (capture stays
          in the adapter module; the runner stays I/O-free -- ADR-0016),
        * renders the visible response blocks plus the flag buttons carrying the
          same id, so a clicked flag attaches to the record appended here.

        Returns ``(interaction_id, final_response, reply_blocks)``. The caller
        owns the actual posting (``say`` for the adapter, ``chat.postMessage``
        for the driver) and any error/fallback handling. Exceptions propagate to
        the caller -- :meth:`on_user_message` wraps this in its Runtime Fallback
        path.
        """
        internal_identity = self.internal_identity_resolver(user)
        interaction_id = uuid.uuid4().hex
        started_at = time.monotonic()
        timestamp = datetime.datetime.now(datetime.UTC).isoformat()
        with self.connection_factory() as connection:
            result = self.answer_path(
                connection,
                text,
                internal_identity,
                set_status,
            )
        final_response = final_response_from_workflow_result(result)
        self._record_interaction(
            lambda: interaction_record.build_interaction_record(
                interaction_id=interaction_id,
                timestamp=timestamp,
                latency_ms=_latency_ms(started_at),
                user=user,
                question=text,
                qa_case_id=qa_case_id,
                qa_review_context=qa_review_context,
                model=self.model_label,
                result=result,
            ),
        )
        reply_blocks = build_reply_blocks(
            question=text,
            response_blocks=visible_response_blocks(final_response),
            interaction_id=interaction_id,
            qa_review_context=qa_review_context,
        )
        return interaction_id, final_response, reply_blocks

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
        started_at = time.monotonic()
        timestamp = datetime.datetime.now(datetime.UTC).isoformat()
        try:
            _interaction_id, final_response, reply_blocks = self.answer_and_render(
                text=text,
                user=user,
                set_status=set_status,
            )
            say(final_response.text, blocks=reply_blocks)
        except Exception as error:
            # Bind to a stable local: `except ... as error` clears `error` at
            # the end of the block, so the record-building thunk closes over
            # this name instead (the thunk runs synchronously, but this also
            # keeps it lexically valid).
            caught = error
            # The success id is minted inside answer_and_render and is lost when
            # it raises, so the crash reply gets its own fresh id; the error
            # record and the fallback's flag buttons share it so the crash reply
            # stays flaggable.
            interaction_id = uuid.uuid4().hex
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
            self._record_runtime_error(
                interaction_id=interaction_id,
                timestamp=timestamp,
                latency_ms=_latency_ms(started_at),
                user=user,
                question=text,
                error=caught,
            )
            # Log first, then deliver the Runtime Fallback Message. If this `say`
            # itself raises we let it propagate: the maintainer log already
            # exists. The fallback is NOT a Non-Answer. It still carries the flag
            # buttons (its error record exists) so a crash reply is flaggable.
            say(
                RUNTIME_FALLBACK_MESSAGE,
                blocks=build_runtime_fallback_blocks(
                    question=text,
                    interaction_id=interaction_id,
                ),
            )

    def record_runtime_error(
        self,
        *,
        question: str,
        user: str,
        error: BaseException,
        qa_review_context: QAReviewContext | None = None,
    ) -> str:
        interaction_id = uuid.uuid4().hex
        timestamp = datetime.datetime.now(datetime.UTC).isoformat()
        self._record_runtime_error(
            interaction_id=interaction_id,
            timestamp=timestamp,
            latency_ms=0,
            user=user,
            question=question,
            error=error,
            qa_review_context=qa_review_context,
        )
        return interaction_id

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

    def _record_runtime_error(
        self,
        *,
        interaction_id: str,
        timestamp: str,
        latency_ms: int,
        user: str,
        question: str,
        error: BaseException,
        qa_review_context: QAReviewContext | None = None,
    ) -> None:
        self._record_interaction(
            lambda: interaction_record.build_error_record(
                interaction_id=interaction_id,
                timestamp=timestamp,
                latency_ms=latency_ms,
                user=user,
                question=question,
                model=self.model_label,
                error=error,
                qa_review_context=qa_review_context,
            ),
        )

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
import json
import logging
import pathlib
import time
import typing
import uuid

import duckdb
import pandas as pd

import data_assistant.access_controller as access_controller
import data_assistant.assistant_thread_pointer as assistant_thread_pointer
import data_assistant.interaction_log as interaction_log
import data_assistant.known_qa_issues as known_qa_issues
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

# --- Flag buttons (issue #111; investigate category added in issue #123) -----
# Every Assistant reply carries three flag buttons so a maintainer can mark a
# response in place; a click flags the Interaction Log record (by id), which the
# maintainer later pastes into Claude Code ("look at the flagged correctness
# cases"). The action_id -> category map is the SINGLE source of truth shared by
# the button-builder and the block_actions handler; categories are exactly the
# interaction_log.FLAG_VOCABULARY.
FLAG_CORRECTNESS_ACTION_ID: typing.Final[str] = "flag_correctness"
FLAG_FORMATTING_ACTION_ID: typing.Final[str] = "flag_formatting"
FLAG_INVESTIGATE_ACTION_ID: typing.Final[str] = "flag_investigate"
QA_ADD_NOTE_ACTION_ID: typing.Final[str] = "qa_add_note"
QA_DONE_ACTION_ID: typing.Final[str] = "qa_done"

ACTION_ID_TO_CATEGORY: typing.Final[dict[str, str]] = {
    FLAG_CORRECTNESS_ACTION_ID: "correctness",
    FLAG_FORMATTING_ACTION_ID: "formatting",
    FLAG_INVESTIGATE_ACTION_ID: "investigate",
}
FLAGGED_INTERACTION_LOG_PREFIX: typing.Final[str] = (
    "data_assistant.flagged_interaction "
)

# Seam type for the pure block_actions core. ``FlagStore`` binds to
# ``interaction_log.flag_interaction(.., path=log_path)`` (returns False on an
# unknown id).
FlagStore: typing.TypeAlias = collections_abc.Callable[[str, str], bool]
DeleteMessage: typing.TypeAlias = collections_abc.Callable[[str, str], object | None]
NoteStore: typing.TypeAlias = collections_abc.Callable[[str, str], bool]

# block_id of the context block that shows which categories a reply has been
# flagged with. We RE-RENDER the Assistant reply in place on each click (Slack's
# Assistant surface does not show ``response_url`` ephemerals inline -- they leak
# into the History pane as unread items), so the confirmation lives as a status
# line appended to the same message. A stable block_id lets a second click find
# and replace the prior status block instead of stacking duplicates.
FLAG_STATUS_BLOCK_ID: typing.Final[str] = "flag_status"
_FLAG_STATUS_PREFIX: typing.Final[str] = "✓ Flagged: "
QA_REVIEW_NOTE_CALLBACK_ID: typing.Final[str] = "qa_review_note_submit"
QA_REVIEW_NOTE_BLOCK_ID: typing.Final[str] = "qa_review_note"
QA_REVIEW_NOTE_ACTION_ID: typing.Final[str] = "qa_review_note_input"

# Every reply leads with a small grey echo of the question so a reader can pair a
# response back to what was asked. We cap the echoed text to keep the context
# line short; the FULL question still lands in the Interaction Log ``question``
# field, so truncation here is purely cosmetic.
QUESTION_ECHO_MAX_CHARS: typing.Final[int] = 200
_QUESTION_ECHO_PREFIX: typing.Final[str] = "❓ "
_QA_FLAG_CATEGORY_EMOJI: typing.Final[dict[str, str]] = {
    "correctness": "🚩",
    "formatting": "🎨",
    "investigate": "🔎",
}


def _flag_button_elements(interaction_id: str) -> list[dict[str, object]]:
    return [
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
        {
            "type": "button",
            "action_id": FLAG_INVESTIGATE_ACTION_ID,
            "text": {"type": "plain_text", "text": "🔎 Investigate"},
            "value": interaction_id,
        },
    ]


def flag_action_blocks(interaction_id: str) -> tuple[contracts.SlackBlock, ...]:
    """Build the Slack ``actions`` block with the three flag buttons.

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
            "elements": _flag_button_elements(interaction_id),
        },
    )


def qa_action_blocks(interaction_id: str) -> tuple[contracts.SlackBlock, ...]:
    return (
        {
            "type": "actions",
            "block_id": f"qa_actions:{interaction_id}",
            "elements": [
                *_flag_button_elements(interaction_id),
                {
                    "type": "button",
                    "action_id": QA_ADD_NOTE_ACTION_ID,
                    "text": {"type": "plain_text", "text": "📝 Add note"},
                    "value": interaction_id,
                },
                {
                    "type": "button",
                    "action_id": QA_DONE_ACTION_ID,
                    "text": {"type": "plain_text", "text": "✅ Done"},
                    "value": interaction_id,
                },
            ],
        },
    )


def _flag_status_block(categories: tuple[str, ...]) -> contracts.SlackBlock:
    """Build the context block summarizing which categories were flagged."""
    return {
        "type": "context",
        "block_id": FLAG_STATUS_BLOCK_ID,
        "elements": [
            {
                "type": "mrkdwn",
                "text": _FLAG_STATUS_PREFIX + ", ".join(categories),
            }
        ],
    }


def _question_echo_block(question: str) -> contracts.SlackBlock:
    """Build the leading context block that echoes the original question.

    Renders small + grey above the answer body so a reader can pair a reply to
    its question. The text is truncated to :data:`QUESTION_ECHO_MAX_CHARS` with a
    ``…`` suffix when over the cap -- the untruncated question still lands in the
    Interaction Log ``question`` field, so this trim is cosmetic only.
    """
    if len(question) > QUESTION_ECHO_MAX_CHARS:
        question = question[:QUESTION_ECHO_MAX_CHARS] + "…"
    return {
        "type": "context",
        "elements": [{"type": "mrkdwn", "text": _QUESTION_ECHO_PREFIX + question}],
    }


def _parse_flag_status(block: contracts.SlackBlock) -> tuple[str, ...]:
    """Recover the categories from a status block we previously rendered.

    Reads our own ``"✓ Flagged: a, b"`` text back into a category tuple so a
    second click can MERGE its category with the ones already shown rather than
    overwrite them. Only categories in :data:`interaction_log.FLAG_VOCABULARY`
    survive -- anything unexpected in the text is ignored defensively.
    """
    elements = block.get("elements")
    if not isinstance(elements, list) or not elements:
        return ()
    first = typing.cast("list[object]", elements)[0]
    if not isinstance(first, dict):
        return ()
    text = typing.cast("dict[str, object]", first).get("text", "")
    if not isinstance(text, str) or not text.startswith(_FLAG_STATUS_PREFIX):
        return ()
    body = text[len(_FLAG_STATUS_PREFIX) :]
    found = {part.strip() for part in body.split(",")}
    return tuple(c for c in interaction_log.FLAG_VOCABULARY if c in found)


def render_flagged_message_blocks(
    *,
    blocks: collections_abc.Sequence[contracts.SlackBlock],
    category: str,
    found: bool,
) -> list[contracts.SlackBlock]:
    """Re-render an Assistant reply's blocks with ``category`` marked flagged.

    Keeps every original block (answer body AND the flag buttons, so the other
    category stays clickable) and appends -- or refreshes -- a single status
    context block listing the cumulative flagged categories in vocabulary order.
    A second click on a different button merges, so the line reads
    ``"✓ Flagged: correctness, formatting"``; a duplicate click is a no-op.

    ``found is False`` (id not in the log -- e.g. a rotated record) leaves the
    blocks untouched: re-rendering the message as-is is a benign no-op, far
    better than crashing or leaking a stray notification on a dead click.
    """
    kept = [b for b in blocks if b.get("block_id") != FLAG_STATUS_BLOCK_ID]
    if not found:
        return kept
    prior: tuple[str, ...] = ()
    for block in blocks:
        if block.get("block_id") == FLAG_STATUS_BLOCK_ID:
            prior = _parse_flag_status(block)
            break
    merged = {*prior, category}
    ordered = tuple(c for c in interaction_log.FLAG_VOCABULARY if c in merged)
    return [*kept, _flag_status_block(ordered)]


def apply_flag(
    *,
    action_id: str,
    interaction_id: str,
    blocks: collections_abc.Sequence[contracts.SlackBlock],
    flag_store: FlagStore,
) -> list[contracts.SlackBlock] | None:
    """Pure block_actions core: flag the record, return the re-rendered blocks.

    Maps ``action_id`` to its flag category, calls ``flag_store`` to persist the
    flag, and returns the message's blocks re-rendered with the new flag status
    (the caller hands these to ``respond(.., replace_original=True)``). An
    unmapped ``action_id`` returns ``None`` -- a defensive no-op that updates
    nothing and never crashes on a stray click.
    """
    category = ACTION_ID_TO_CATEGORY.get(action_id)
    if category is None:
        return None
    found = flag_store(interaction_id, category)
    return render_flagged_message_blocks(blocks=blocks, category=category, found=found)


def _string_field(mapping: object, key: str) -> str:
    if not isinstance(mapping, dict):
        return ""
    value = typing.cast("dict[str, object]", mapping).get(key)
    return value if isinstance(value, str) else ""


def qa_done_target(body: dict[str, typing.Any]) -> tuple[str, str]:
    """Extract Slack delete coordinates from a QA-done action payload."""
    channel_id = _string_field(body.get("channel"), "id")
    container_message_ts = _string_field(body.get("container"), "message_ts")
    message_ts = _string_field(body.get("message"), "ts")
    return channel_id, container_message_ts or message_ts


def apply_qa_done(
    *,
    body: dict[str, typing.Any],
    delete_message: DeleteMessage,
) -> bool:
    """Pure QA-done core: delete clicked QA review message when payload is usable."""
    channel_id, message_ts = qa_done_target(body)
    if not channel_id or not message_ts:
        return False
    try:
        delete_message(channel_id, message_ts)
    except Exception:
        logger.exception("Failed to delete QA review message.")
        return False
    return True


def build_qa_review_note_modal(
    *,
    interaction_id: str,
    existing_note: str,
    channel_id: str = "",
    message_ts: str = "",
    message_text: str = "",
) -> dict[str, object]:
    metadata: dict[str, object] = {
        "interaction_id": interaction_id,
    }
    if channel_id:
        metadata["channel_id"] = channel_id
    if message_ts:
        metadata["message_ts"] = message_ts
    if message_text:
        metadata["message_text"] = message_text
    return {
        "type": "modal",
        "callback_id": QA_REVIEW_NOTE_CALLBACK_ID,
        "private_metadata": json.dumps(metadata),
        "title": {"type": "plain_text", "text": "QA Review Note"},
        "submit": {"type": "plain_text", "text": "Save"},
        "close": {"type": "plain_text", "text": "Cancel"},
        "blocks": [
            {
                "type": "input",
                "block_id": QA_REVIEW_NOTE_BLOCK_ID,
                "label": {"type": "plain_text", "text": "Note"},
                "element": {
                    "type": "plain_text_input",
                    "action_id": QA_REVIEW_NOTE_ACTION_ID,
                    "multiline": True,
                    "initial_value": existing_note,
                },
            }
        ],
    }


def apply_qa_review_note_save(
    *,
    body: dict[str, typing.Any],
    note_store: NoteStore,
) -> dict[str, object] | None:
    view_obj = body.get("view")
    if not isinstance(view_obj, dict):
        return None
    view = typing.cast("dict[str, object]", view_obj)
    metadata = _qa_review_note_metadata(view.get("private_metadata"))
    interaction_id = metadata.get("interaction_id")
    if not isinstance(interaction_id, str) or not interaction_id:
        return None
    note = _qa_review_note_value(view.get("state"))
    if note is None:
        return None
    changed = note_store(interaction_id, note)
    if not changed:
        return None
    result: dict[str, object] = {"interaction_id": interaction_id}
    for field in ("channel_id", "message_ts", "message_text"):
        value = metadata.get(field)
        if isinstance(value, str) and value:
            result[field] = value
    return result


def _qa_review_note_metadata(metadata: object) -> dict[str, object]:
    if not isinstance(metadata, str) or not metadata:
        return {}
    try:
        loaded = json.loads(metadata)
    except json.JSONDecodeError:
        return {}
    return typing.cast("dict[str, object]", loaded) if isinstance(loaded, dict) else {}


def _qa_review_note_value(state: object) -> str | None:
    if not isinstance(state, dict):
        return None
    state_dict = typing.cast("dict[str, object]", state)
    values = state_dict.get("values")
    if not isinstance(values, dict):
        return None
    values_dict = typing.cast("dict[str, object]", values)
    block = values_dict.get(QA_REVIEW_NOTE_BLOCK_ID)
    if not isinstance(block, dict):
        return None
    block_dict = typing.cast("dict[str, object]", block)
    action = block_dict.get(QA_REVIEW_NOTE_ACTION_ID)
    if not isinstance(action, dict):
        return None
    action_dict = typing.cast("dict[str, object]", action)
    value = action_dict.get("value", "")
    return value if isinstance(value, str) else ""


def render_note_saved_blocks(
    blocks: object,
) -> list[contracts.SlackBlock]:
    if not isinstance(blocks, list):
        return []
    raw_blocks = typing.cast("list[object]", blocks)
    rendered: list[contracts.SlackBlock] = []
    for block_obj in raw_blocks:
        if not isinstance(block_obj, dict):
            return []
        block_dict = typing.cast("dict[str, object]", block_obj)
        rendered.append(dict(block_dict))
    if not rendered:
        return rendered
    first = rendered[0]
    if first.get("type") != "context":
        return rendered
    elements = first.get("elements")
    if not isinstance(elements, list) or not elements:
        return rendered
    lead = typing.cast("list[object]", elements)[0]
    if not isinstance(lead, dict):
        return rendered
    lead_dict = typing.cast("dict[str, object]", lead)
    text = lead_dict.get("text")
    if not isinstance(text, str):
        return rendered
    if "Note saved" not in text:
        lead_dict["text"] = f"{text} • Note saved"
    return rendered


def flag_interaction_for_triage(
    *,
    interaction_id: str,
    category: str,
    log_path: pathlib.Path,
) -> bool:
    """Flag one record and mirror its sanitized payload into app logs.

    Render exposes application logs to our tooling, but not arbitrary files on a
    worker. Emitting only maintainer-flagged records keeps normal interaction
    logs local while making flagged cases remotely triageable.
    """
    changed = interaction_log.flag_interaction(
        interaction_id,
        category,
        path=log_path,
    )
    if changed:
        _log_flagged_interaction_for_triage(
            interaction_id=interaction_id,
            log_path=log_path,
        )
    return changed


def _log_flagged_interaction_for_triage(
    *,
    interaction_id: str,
    log_path: pathlib.Path,
) -> None:
    try:
        record = interaction_log.find_interaction(interaction_id, path=log_path)
        if record is None:
            payload = {"id": interaction_id, "missing": True}
        else:
            payload = record
        logger.warning(
            "%s%s",
            FLAGGED_INTERACTION_LOG_PREFIX,
            json.dumps(payload, sort_keys=True),
        )
    except Exception:
        logger.exception("Failed to mirror flagged Interaction Log record.")


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
KnownIssueReference = known_qa_issues.KnownQAIssue


@dataclasses.dataclass(frozen=True)
class QAReviewContext:
    battery_path: str
    qa_case_id: str | None
    known_issues: tuple[KnownIssueReference, ...] = ()
    position: int | None = None
    total: int | None = None
    note_saved: bool = False


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


def _visible_response_blocks(
    final_response: contracts.FinalResponse,
) -> tuple[contracts.SlackBlock, ...]:
    """Return blocks that visibly carry the response body in Slack."""
    blocks = tuple(final_response.blocks)
    if blocks:
        return blocks
    return (
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": final_response.text},
        },
    )


def _latency_ms(started_at: float) -> int:
    return int((time.monotonic() - started_at) * 1000)


def _interaction_record(
    *,
    interaction_id: str,
    timestamp: str,
    latency_ms: int,
    user: str,
    question: str,
    qa_case_id: str | None,
    qa_review_context: QAReviewContext | None,
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
    if qa_case_id is not None:
        record["qa_case_id"] = qa_case_id
    _apply_qa_review_context(record, qa_review_context=qa_review_context)
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
    qa_review_context: QAReviewContext | None = None,
) -> dict[str, object]:
    """Build the Interaction Log record for a crashed answer path."""
    record: dict[str, object] = {
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
    _apply_qa_review_context(record, qa_review_context=qa_review_context)
    return record


def _apply_qa_review_context(
    record: dict[str, object],
    *,
    qa_review_context: QAReviewContext | None,
) -> None:
    if qa_review_context is None:
        return
    record["source"] = "qa_review"
    record["battery_path"] = qa_review_context.battery_path
    if qa_review_context.qa_case_id is None:
        return
    record["qa_case_id"] = qa_review_context.qa_case_id
    record["known_issues"] = [
        {
            "issue_number": issue.issue_number,
            "flag_category": issue.flag_category,
        }
        for issue in qa_review_context.known_issues
    ]


def build_runtime_fallback_blocks(
    *,
    question: str,
    interaction_id: str,
    qa_review_context: QAReviewContext | None = None,
) -> tuple[contracts.SlackBlock, ...]:
    fallback_section: contracts.SlackBlock = {
        "type": "section",
        "text": {"type": "mrkdwn", "text": RUNTIME_FALLBACK_MESSAGE},
    }
    return _reply_blocks(
        question=question,
        response_blocks=(fallback_section,),
        interaction_id=interaction_id,
        qa_review_context=qa_review_context,
    )


def _qa_review_header_block(
    qa_review_context: QAReviewContext,
) -> contracts.SlackBlock:
    parts: list[str] = []
    if (
        qa_review_context.position is not None
        and qa_review_context.total is not None
        and qa_review_context.total > 0
    ):
        parts.append(f"QA {qa_review_context.position}/{qa_review_context.total}")
    else:
        parts.append("QA Review")
    if qa_review_context.qa_case_id is not None:
        parts.append(f"Case `{qa_review_context.qa_case_id}`")
    if qa_review_context.known_issues:
        known_issues = ", ".join(
            (
                f"#{issue.issue_number} "
                f"{_QA_FLAG_CATEGORY_EMOJI.get(issue.flag_category, '🚩')}"
            )
            for issue in qa_review_context.known_issues
        )
        parts.append(f"Known QA Issues: {known_issues}")
    if qa_review_context.note_saved:
        parts.append("Note saved")
    return {
        "type": "context",
        "elements": [{"type": "mrkdwn", "text": " • ".join(parts)}],
    }


def _reply_blocks(
    *,
    question: str,
    response_blocks: collections_abc.Sequence[contracts.SlackBlock],
    interaction_id: str,
    qa_review_context: QAReviewContext | None,
) -> tuple[contracts.SlackBlock, ...]:
    leading_blocks: tuple[contracts.SlackBlock, ...]
    action_blocks: tuple[contracts.SlackBlock, ...]
    if qa_review_context is None:
        leading_blocks = ()
        action_blocks = flag_action_blocks(interaction_id)
    else:
        leading_blocks = (_qa_review_header_block(qa_review_context),)
        action_blocks = qa_action_blocks(interaction_id)
    return (
        leading_blocks
        + (_question_echo_block(question),)
        + tuple(response_blocks)
        + action_blocks
    )


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
        "group_by": (
            []
            if data_request.group_by_field is None
            else [data_request.group_by_field.label]
        ),
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
        "group_by": []
        if question_frame.group_by_field is None
        else [question_frame.group_by_field],
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
            lambda: _interaction_record(
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
        reply_blocks = _reply_blocks(
            question=text,
            response_blocks=_visible_response_blocks(final_response),
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
            lambda: _error_record(
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
    the routing identifiers. ``thread_started`` also takes ``context`` so the
    adapter can record the (channel, thread_ts) pointer the QA driver reads.
    """
    from slack_bolt import Assistant

    # Typed as Any: Bolt's decorator signatures are loosely typed and would
    # otherwise leak "partially unknown" through this shim.
    assistant: typing.Any = Assistant()

    def _thread_started(
        context: typing.Any,
        say: Sayer,
        set_suggested_prompts: SuggestedPromptsSetter,
    ) -> None:
        adapter.on_thread_started(
            say=say,
            set_suggested_prompts=set_suggested_prompts,
            channel=context.channel_id or "",
            thread_ts=context.thread_ts or "",
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

    _register_message_actions(app=app, adapter=adapter)


def _register_message_actions(
    *,
    app: typing.Any,
    adapter: AssistantAdapter,
) -> None:
    """Wire the flag buttons' ``block_actions`` listeners (thin untested shim).

    For each flag ``action_id`` we register a Bolt action listener that, over
    Socket Mode: ``ack()``s first, reads the embedded ``interaction_id`` from
    the button ``value`` and the clicked message's ``blocks`` from ``body``,
    binds the ``flag_store`` seam to ``interaction_log.flag_interaction`` (with
    the adapter's ``log_path``), then delegates to the pure ``apply_flag`` for
    the re-rendered blocks. All behavior lives in ``apply_flag``; this shim is
    the only live-API-shaped code here and is intentionally untested.

    Bolt's ``respond`` is bound to the action's ``response_url``; calling
    ``respond(blocks=..., replace_original=True)`` RE-RENDERS the same Assistant
    reply in place -- the answer + buttons stay and a "✓ Flagged" status line is
    appended. ``replace_original=True`` is deliberate: the Assistant surface does
    NOT show ``response_url`` ephemerals inline (they leak into the History pane
    as unread items), so editing the message is the only non-spammy way to
    confirm. Verified against the ``slack_bolt`` 1.28.0 ``Respond.__call__``
    signature (``blocks`` / ``replace_original`` keywords).
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
        message = body.get("message")
        raw_blocks: object = (
            typing.cast("dict[str, object]", message).get("blocks")
            if isinstance(message, dict)
            else None
        )
        original_blocks: collections_abc.Sequence[contracts.SlackBlock] = (
            typing.cast("list[contracts.SlackBlock]", raw_blocks)
            if isinstance(raw_blocks, list)
            else []
        )

        def flag_store(target_id: str, category: str) -> bool:
            return flag_interaction_for_triage(
                interaction_id=target_id,
                category=category,
                log_path=adapter.log_path,
            )

        new_blocks = apply_flag(
            action_id=action_id,
            interaction_id=interaction_id,
            blocks=original_blocks,
            flag_store=flag_store,
        )
        if new_blocks is None:
            return
        # replace_original=True RE-RENDERS the same Assistant reply in place: the
        # answer + buttons stay and a "✓ Flagged" status line is appended. The
        # Assistant surface does not show response_url ephemerals inline (they
        # leak into the History pane as unread items), so editing the message is
        # the only way to confirm without spamming a separate notification.
        respond(blocks=new_blocks, replace_original=True)

    # Register one listener per flag action_id (the single source of truth).
    for flag_action_id in ACTION_ID_TO_CATEGORY:
        app.action(flag_action_id)(_flag_action)

    def _qa_done_action(
        ack: collections_abc.Callable[[], None],
        body: dict[str, typing.Any],
        client: typing.Any,
    ) -> None:
        ack()
        apply_qa_done(
            body=body,
            delete_message=lambda channel, ts: client.chat_delete(
                channel=channel,
                ts=ts,
            ),
        )

    app.action(QA_DONE_ACTION_ID)(_qa_done_action)

    def _qa_add_note_action(
        ack: collections_abc.Callable[[], None],
        body: dict[str, typing.Any],
        client: typing.Any,
    ) -> None:
        ack()
        actions: list[dict[str, typing.Any]] = body.get("actions") or [{}]
        action = actions[0]
        interaction_id = str(action.get("value", ""))
        trigger_id = _string_field(body, "trigger_id")
        if not interaction_id or not trigger_id:
            return
        message = body.get("message")
        if isinstance(message, dict):
            message_dict: dict[str, object] = typing.cast(
                "dict[str, object]",
                message,
            )
        else:
            message_dict = {}
        record = interaction_log.find_interaction(interaction_id, path=adapter.log_path)
        existing_note = ""
        if record is not None:
            note_value = record.get("qa_review_note")
            if isinstance(note_value, str):
                existing_note = note_value
        channel_id, message_ts = qa_done_target(body)
        client.views_open(
            trigger_id=trigger_id,
            view=build_qa_review_note_modal(
                interaction_id=interaction_id,
                existing_note=existing_note,
                channel_id=channel_id,
                message_ts=message_ts,
                message_text=_string_field(message_dict, "text"),
            ),
        )

    app.action(QA_ADD_NOTE_ACTION_ID)(_qa_add_note_action)

    def _qa_review_note_submit(
        ack: collections_abc.Callable[[], None],
        body: dict[str, typing.Any],
        client: typing.Any,
    ) -> None:
        ack()
        result = apply_qa_review_note_save(
            body=body,
            note_store=lambda interaction_id, note: interaction_log.save_qa_review_note(
                interaction_id,
                note,
                path=adapter.log_path,
            ),
        )
        if result is None:
            return
        channel_id = typing.cast("str | None", result.get("channel_id"))
        message_ts = typing.cast("str | None", result.get("message_ts"))
        if not channel_id or not message_ts:
            return
        history = client.conversations_history(
            channel=channel_id,
            latest=message_ts,
            oldest=message_ts,
            inclusive=True,
            limit=1,
        )
        messages = history.get("messages")
        if not isinstance(messages, list) or not messages:
            return
        first_message = typing.cast("list[object]", messages)[0]
        if not isinstance(first_message, dict):
            return
        message = typing.cast("dict[str, object]", first_message)
        raw_blocks = message.get("blocks")
        blocks = render_note_saved_blocks(raw_blocks)
        kwargs: dict[str, object] = {
            "channel": channel_id,
            "ts": message_ts,
            "blocks": blocks,
        }
        message_text = result.get("message_text")
        if isinstance(message_text, str) and message_text:
            kwargs["text"] = message_text
        client.chat_update(**kwargs)

    app.view(QA_REVIEW_NOTE_CALLBACK_ID)(_qa_review_note_submit)

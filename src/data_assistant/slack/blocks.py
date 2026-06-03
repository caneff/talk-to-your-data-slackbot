"""Pure Block-Kit *constructors* for the Slack edge.

Everything here BUILDS Slack blocks; nothing here READS an inbound Slack
payload (that lives in ``payloads``). Dependency flows one way: ``payloads``
imports from ``blocks`` (it consumes :func:`flag_status_block`); ``blocks``
must never import ``payloads`` -- that would create a cycle.

# response_composer is core pipeline, NOT edge chrome: it stays out of slack/
# (moving it would invert the edge->core dependency — ADR-0015).
"""

from __future__ import annotations

import collections.abc as collections_abc
import typing

import data_assistant.workflow.contracts as contracts
from data_assistant.interaction_record import (
    RUNTIME_FALLBACK_MESSAGE,
    QAReviewContext,
)
from data_assistant.slack.prompts import (
    FLAG_CORRECTNESS_ACTION_ID,
    FLAG_FORMATTING_ACTION_ID,
    FLAG_INVESTIGATE_ACTION_ID,
    QA_ADD_NOTE_ACTION_ID,
    QA_DONE_ACTION_ID,
)

# block_id of the context block that shows which categories a reply has been
# flagged with. We RE-RENDER the Assistant reply in place on each click (Slack's
# Assistant surface does not show ``response_url`` ephemerals inline -- they leak
# into the History pane as unread items), so the confirmation lives as a status
# line appended to the same message. A stable block_id lets a second click find
# and replace the prior status block instead of stacking duplicates.
FLAG_STATUS_BLOCK_ID: typing.Final[str] = "flag_status"
FLAG_STATUS_PREFIX: typing.Final[str] = "✓ Flagged: "

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


def flag_status_block(categories: tuple[str, ...]) -> contracts.SlackBlock:
    """Build the context block summarizing which categories were flagged."""
    return {
        "type": "context",
        "block_id": FLAG_STATUS_BLOCK_ID,
        "elements": [
            {
                "type": "mrkdwn",
                "text": FLAG_STATUS_PREFIX + ", ".join(categories),
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


def visible_response_blocks(
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


def reply_blocks(
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
    return reply_blocks(
        question=question,
        response_blocks=(fallback_section,),
        interaction_id=interaction_id,
        qa_review_context=qa_review_context,
    )

"""Slack-edge strings, action-id vocabulary, and the triage-flag mirror.

This module owns the user-facing copy (greeting + suggested prompts), the
``action_id`` constants that the block CONSTRUCTORS (``blocks``) and the Bolt
wiring (``wiring``) both reference, and the triage-flag mirror that flags one
Interaction Log record and emits its sanitized payload into the app logs for
remote triage. It depends on nothing else in ``slack/`` -- everything points
inward at it.
"""

from __future__ import annotations

import json
import logging
import pathlib
import typing

import data_assistant.interaction_log as interaction_log

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

QA_REVIEW_NOTE_CALLBACK_ID: typing.Final[str] = "qa_review_note_submit"
QA_REVIEW_NOTE_BLOCK_ID: typing.Final[str] = "qa_review_note"
QA_REVIEW_NOTE_ACTION_ID: typing.Final[str] = "qa_review_note_input"


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

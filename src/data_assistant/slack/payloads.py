"""Inbound-payload extraction, pure cores, and block *readers*.

Everything here READS a structure that came back from Slack -- an inbound
``block_actions`` body, a clicked message's blocks, a view-submission state --
or runs a pure decision core over it. Block CONSTRUCTORS live in ``blocks``;
this module imports from ``blocks`` (it consumes :func:`flag_status_block`)
but ``blocks`` never imports this module, so the dependency is one-way and
acyclic.
"""

from __future__ import annotations

import collections.abc as collections_abc
import json
import logging
import typing

import data_assistant.interaction_log as interaction_log
import data_assistant.workflow.contracts as contracts
from data_assistant.slack.blocks import (
    FLAG_STATUS_BLOCK_ID,
    FLAG_STATUS_PREFIX,
    flag_status_block,
)
from data_assistant.slack.prompts import (
    ACTION_ID_TO_CATEGORY,
    QA_REVIEW_NOTE_ACTION_ID,
    QA_REVIEW_NOTE_BLOCK_ID,
    QA_REVIEW_NOTE_CALLBACK_ID,
)

logger = logging.getLogger(__name__)

# Seam type for the pure block_actions core. ``FlagStore`` binds to
# ``interaction_log.flag_interaction(.., path=log_path)`` (returns False on an
# unknown id).
FlagStore: typing.TypeAlias = collections_abc.Callable[[str, str], bool]
DeleteMessage: typing.TypeAlias = collections_abc.Callable[[str, str], object | None]
NoteStore: typing.TypeAlias = collections_abc.Callable[[str, str], bool]


def str_at(payload: object, *keys: str) -> str:
    """Walk nested dict keys; return the string at the end or "".

    Returns "" if any hop is missing or not a ``dict``, or if the final value
    is not a ``str``. This single path-getter collapses the repeated
    isinstance/cast walks that used to extract Slack payload fields.
    """
    current: object = payload
    for key in keys:
        if not isinstance(current, dict):
            return ""
        current = typing.cast("dict[str, object]", current).get(key)
    return current if isinstance(current, str) else ""


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
    if not isinstance(text, str) or not text.startswith(FLAG_STATUS_PREFIX):
        return ()
    body = text[len(FLAG_STATUS_PREFIX) :]
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
    return [*kept, flag_status_block(ordered)]


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


def action_target(body: dict[str, typing.Any]) -> tuple[str, str]:
    """(action_id, interaction_id) from the first action in a block_actions body."""
    actions: list[dict[str, typing.Any]] = body.get("actions") or [{}]
    action = actions[0]
    return str(action.get("action_id", "")), str(action.get("value", ""))


def message_blocks(body: dict[str, typing.Any]) -> list[contracts.SlackBlock]:
    """The clicked message's blocks from a block_actions body ([] when absent)."""
    message = body.get("message")
    if not isinstance(message, dict):
        return []
    blocks = typing.cast("dict[str, object]", message).get("blocks")
    return (
        typing.cast("list[contracts.SlackBlock]", blocks)
        if isinstance(blocks, list)
        else []
    )


def qa_done_target(body: dict[str, typing.Any]) -> tuple[str, str]:
    """Extract Slack delete coordinates from a QA-done action payload."""
    channel_id = str_at(body, "channel", "id")
    container_message_ts = str_at(body, "container", "message_ts")
    message_ts = str_at(body, "message", "ts")
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
    """Read the submitted note string, or ``None`` when the input is absent.

    Distinguishes "the note input block is missing from the submission" (return
    ``None`` -> :func:`apply_qa_review_note_save` skips the save) from "the input
    is present but empty" (return ``""`` -> an empty note is a legitimate save).
    :func:`str_at` collapses both to ``""``, so this thin wrapper checks the
    presence of the action dict first to preserve the original None branch.
    """
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
    if QA_REVIEW_NOTE_ACTION_ID not in block_dict:
        return None
    # The action input is present, so this is a real save: str_at reads the
    # ``value`` (present-empty collapses to "", a legitimate empty-note save).
    return str_at(block_dict, QA_REVIEW_NOTE_ACTION_ID, "value")


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

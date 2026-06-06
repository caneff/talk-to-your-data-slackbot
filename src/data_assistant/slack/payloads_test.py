"""Tests for the Slack-edge inbound-payload cores and block readers."""

from __future__ import annotations

import collections.abc
import json
import typing

import pytest

import data_assistant.interaction_log as interaction_log
import data_assistant.slack.blocks as blocks
import data_assistant.slack.payloads as payloads
import data_assistant.slack.prompts as prompts
import data_assistant.workflow.contracts as contracts


def _button_elements(block: contracts.SlackBlock) -> list[dict[str, object]]:
    elements = block.get("elements")
    assert isinstance(elements, list)
    typed: list[dict[str, object]] = []
    for element in typing.cast("list[object]", elements):
        assert isinstance(element, dict)
        typed.append(typing.cast("dict[str, object]", element))
    return typed


def _action_ids_in(
    block_list: collections.abc.Sequence[contracts.SlackBlock],
) -> set[str]:
    action_ids: set[str] = set()
    for block in block_list:
        if block.get("type") != "actions":
            continue
        for element in _button_elements(block):
            action_id = element["action_id"]
            assert isinstance(action_id, str)
            action_ids.add(action_id)
    return action_ids


def _context_text(block: contracts.SlackBlock) -> str:
    assert block.get("type") == "context"
    elements = block.get("elements")
    assert isinstance(elements, list) and elements
    first = typing.cast("list[object]", elements)[0]
    assert isinstance(first, dict)
    text = typing.cast("dict[str, object]", first).get("text")
    assert isinstance(text, str)
    return text


class _RecordingFlagStore:
    """Fake toggle seam: records calls, returns a fixed result."""

    def __init__(
        self,
        *,
        result: interaction_log.ToggleFlagResult = (
            interaction_log.ToggleFlagResult.SELECTED
        ),
    ) -> None:
        self.calls: list[tuple[str, str]] = []
        self._result = result

    def __call__(
        self,
        interaction_id: str,
        category: str,
    ) -> interaction_log.ToggleFlagResult:
        self.calls.append((interaction_id, category))
        return self._result


class _RecordingDeleteMessage:
    """Fake ``chat_delete`` seam: records calls, optionally raises."""

    def __init__(self, *, error: BaseException | None = None) -> None:
        self.calls: list[tuple[str, str]] = []
        self._error = error

    def __call__(self, channel: str, ts: str) -> None:
        self.calls.append((channel, ts))
        if self._error is not None:
            raise self._error


class _RecordingNoteStore:
    def __init__(self, *, result: bool = True) -> None:
        self.calls: list[tuple[str, str]] = []
        self._result = result

    def __call__(self, interaction_id: str, note: str) -> bool:
        self.calls.append((interaction_id, note))
        return self._result


def _answer_blocks() -> list[dict[str, object]]:
    """A minimal Assistant reply: a section + the flag buttons."""
    return [
        {"type": "section", "text": {"type": "mrkdwn", "text": "the answer"}},
        *blocks.flag_action_blocks("abc123"),
    ]


def _button_by_action_id(
    block_list: collections.abc.Sequence[contracts.SlackBlock],
) -> dict[str, dict[str, object]]:
    buttons: dict[str, dict[str, object]] = {}
    for block in block_list:
        if block.get("type") != "actions":
            continue
        for element in _button_elements(block):
            action_id = element["action_id"]
            assert isinstance(action_id, str)
            buttons[action_id] = element
    return buttons


def _qa_done_body(
    *,
    channel_id: object = "C123",
    container_message_ts: object = "1748880000.123456",
    message_ts: object = "1748880000.123456",
    value: object = "interaction-123",
) -> dict[str, object]:
    return {
        "channel": {"id": channel_id},
        "container": {"message_ts": container_message_ts},
        "message": {
            "ts": message_ts,
            "blocks": list(blocks.qa_action_blocks("interaction-123")),
        },
        "actions": [
            {
                "action_id": prompts.QA_DONE_ACTION_ID,
                "value": value,
            }
        ],
    }


def _qa_note_view_state(note: str) -> dict[str, object]:
    return {
        "values": {
            prompts.QA_REVIEW_NOTE_BLOCK_ID: {
                prompts.QA_REVIEW_NOTE_ACTION_ID: {
                    "type": "plain_text_input",
                    "value": note,
                }
            }
        }
    }


def test_apply_flag_toggles_on_selected_button_and_keeps_answer_and_buttons() -> None:
    store = _RecordingFlagStore()
    original = _answer_blocks()

    new_blocks = payloads.apply_flag(
        action_id=prompts.FLAG_CORRECTNESS_ACTION_ID,
        interaction_id="abc123",
        blocks=original,
        flag_store=store,
    )

    assert store.calls == [("abc123", "correctness")]
    assert new_blocks is not None
    # The answer body and the flag buttons survive (buttons stay clickable).
    assert new_blocks[0] == original[0]
    assert _action_ids_in(new_blocks) == {
        prompts.FLAG_CORRECTNESS_ACTION_ID,
        prompts.FLAG_FORMATTING_ACTION_ID,
        prompts.FLAG_INVESTIGATE_ACTION_ID,
    }
    correctness_button = _button_by_action_id(new_blocks)[
        prompts.FLAG_CORRECTNESS_ACTION_ID
    ]
    assert correctness_button["text"] == {"type": "plain_text", "text": "✓ Incorrect"}
    assert correctness_button["style"] == "danger"
    assert all(block.get("block_id") != "flag_status" for block in new_blocks)


def test_apply_flag_second_category_marks_both_buttons_in_vocabulary_order() -> None:
    store = _RecordingFlagStore()
    after_first = payloads.apply_flag(
        action_id=prompts.FLAG_FORMATTING_ACTION_ID,
        interaction_id="abc123",
        blocks=_answer_blocks(),
        flag_store=store,
    )
    assert after_first is not None
    formatting_button = _button_by_action_id(after_first)[
        prompts.FLAG_FORMATTING_ACTION_ID
    ]
    assert formatting_button["text"] == {
        "type": "plain_text",
        "text": "✓ Formatting",
    }

    after_second = payloads.apply_flag(
        action_id=prompts.FLAG_CORRECTNESS_ACTION_ID,
        interaction_id="abc123",
        blocks=after_first,
        flag_store=store,
    )

    assert after_second is not None
    buttons = _button_by_action_id(after_second)
    assert buttons[prompts.FLAG_CORRECTNESS_ACTION_ID]["text"] == {
        "type": "plain_text",
        "text": "✓ Incorrect",
    }
    assert buttons[prompts.FLAG_FORMATTING_ACTION_ID]["text"] == {
        "type": "plain_text",
        "text": "✓ Formatting",
    }


def test_apply_flag_toggles_off_selected_current_run_category() -> None:
    selected = blocks.flag_action_blocks(
        "abc123",
        selected_categories=("correctness",),
    )
    original: list[contracts.SlackBlock] = [
        {"type": "section", "text": {"type": "mrkdwn", "text": "the answer"}},
        *selected,
    ]

    new_blocks = payloads.apply_flag(
        action_id=prompts.FLAG_CORRECTNESS_ACTION_ID,
        interaction_id="abc123",
        blocks=original,
        flag_store=_RecordingFlagStore(
            result=interaction_log.ToggleFlagResult.UNSELECTED
        ),
    )

    assert new_blocks is not None
    correctness_button = _button_by_action_id(new_blocks)[
        prompts.FLAG_CORRECTNESS_ACTION_ID
    ]
    assert correctness_button["text"] == {
        "type": "plain_text",
        "text": "🚩 Incorrect",
    }
    assert "style" not in correctness_button


def test_apply_flag_known_only_qa_selection_is_visual_noop() -> None:
    original: list[contracts.SlackBlock] = [
        {"type": "context", "elements": [{"type": "mrkdwn", "text": "QA Review"}]},
        {"type": "section", "text": {"type": "mrkdwn", "text": "the answer"}},
        *blocks.qa_action_blocks(
            "abc123",
            selected_categories=("correctness",),
            locked_categories=("correctness",),
        ),
    ]
    store = _RecordingFlagStore()

    new_blocks = payloads.apply_flag(
        action_id=prompts.FLAG_CORRECTNESS_ACTION_ID,
        interaction_id="abc123",
        blocks=original,
        flag_store=store,
    )

    assert store.calls == []
    assert new_blocks == original


def test_apply_flag_unknown_id_leaves_blocks_unchanged() -> None:
    store = _RecordingFlagStore(result=interaction_log.ToggleFlagResult.NOT_FOUND)
    original = _answer_blocks()

    new_blocks = payloads.apply_flag(
        action_id=prompts.FLAG_CORRECTNESS_ACTION_ID,
        interaction_id="missing",
        blocks=original,
        flag_store=store,
    )

    # Store was consulted, but an unknown id adds no status line (benign no-op).
    assert store.calls == [("missing", "correctness")]
    assert new_blocks is not None
    assert new_blocks == original
    assert _action_ids_in(new_blocks) == {
        prompts.FLAG_CORRECTNESS_ACTION_ID,
        prompts.FLAG_FORMATTING_ACTION_ID,
        prompts.FLAG_INVESTIGATE_ACTION_ID,
    }


def test_apply_flag_unknown_action_id_is_defensive_noop() -> None:
    store = _RecordingFlagStore()

    new_blocks = payloads.apply_flag(
        action_id="not_a_flag_button",
        interaction_id="abc123",
        blocks=_answer_blocks(),
        flag_store=store,
    )

    # Defensive: an unmapped action_id never flags, returns None (nothing to do).
    assert store.calls == []
    assert new_blocks is None


def test_apply_qa_done_deletes_message_from_normal_payload() -> None:
    delete_message = _RecordingDeleteMessage()

    deleted = payloads.apply_qa_done(
        body=_qa_done_body(),
        delete_message=delete_message,
    )

    assert deleted is True
    assert delete_message.calls == [("C123", "1748880000.123456")]


def test_apply_qa_done_ignores_missing_or_unrelated_button_value() -> None:
    delete_message = _RecordingDeleteMessage()

    deleted = payloads.apply_qa_done(
        body=_qa_done_body(value=None),
        delete_message=delete_message,
    )

    assert deleted is True
    assert delete_message.calls == [("C123", "1748880000.123456")]


def test_apply_qa_done_falls_back_to_message_ts() -> None:
    delete_message = _RecordingDeleteMessage()

    deleted = payloads.apply_qa_done(
        body=_qa_done_body(
            container_message_ts=None,
            message_ts="1748889999.000001",
        ),
        delete_message=delete_message,
    )

    assert deleted is True
    assert delete_message.calls == [("C123", "1748889999.000001")]


@pytest.mark.parametrize(
    ("channel_id", "container_message_ts", "message_ts"),
    [
        (None, "1748880000.123456", "1748880000.123456"),
        ("", "1748880000.123456", "1748880000.123456"),
        ("C123", None, None),
        ("C123", "", ""),
    ],
)
def test_apply_qa_done_safe_noop_for_malformed_payload(
    channel_id: object,
    container_message_ts: object,
    message_ts: object,
) -> None:
    delete_message = _RecordingDeleteMessage()

    deleted = payloads.apply_qa_done(
        body=_qa_done_body(
            channel_id=channel_id,
            container_message_ts=container_message_ts,
            message_ts=message_ts,
        ),
        delete_message=delete_message,
    )

    assert deleted is False
    assert delete_message.calls == []


def test_apply_qa_done_catches_delete_failure_without_crashing() -> None:
    delete_message = _RecordingDeleteMessage(error=RuntimeError("Slack down"))

    deleted = payloads.apply_qa_done(
        body=_qa_done_body(),
        delete_message=delete_message,
    )

    assert deleted is False
    assert delete_message.calls == [("C123", "1748880000.123456")]


def test_action_target_reads_first_action_id_and_value() -> None:
    body = {
        "actions": [
            {"action_id": prompts.QA_DONE_ACTION_ID, "value": "interaction-123"},
            {"action_id": "ignored", "value": "ignored"},
        ]
    }
    assert payloads.action_target(body) == (
        prompts.QA_DONE_ACTION_ID,
        "interaction-123",
    )


def test_action_target_empty_actions_returns_empty_pair() -> None:
    assert payloads.action_target({"actions": []}) == ("", "")


def test_action_target_missing_keys_returns_empty_pair() -> None:
    # No ``actions`` key at all, and an action with no action_id/value.
    assert payloads.action_target({}) == ("", "")
    assert payloads.action_target({"actions": [{}]}) == ("", "")


def test_message_blocks_returns_clicked_message_blocks() -> None:
    blocks_list = list(blocks.qa_action_blocks("interaction-123"))
    body = {"message": {"ts": "1748880000.123456", "blocks": blocks_list}}
    assert payloads.message_blocks(body) == blocks_list


def test_message_blocks_missing_message_returns_empty_list() -> None:
    assert payloads.message_blocks({}) == []
    assert payloads.message_blocks({"message": "not-a-dict"}) == []


def test_message_blocks_non_list_blocks_returns_empty_list() -> None:
    assert payloads.message_blocks({"message": {"blocks": "not-a-list"}}) == []
    assert payloads.message_blocks({"message": {}}) == []


def test_build_qa_review_note_modal_prefills_existing_note_and_metadata() -> None:
    view = payloads.build_qa_review_note_modal(
        interaction_id="interaction-123",
        existing_note="Existing note",
        channel_id="C123",
        message_ts="1748880000.123456",
        message_text="QA answer text",
    )

    assert view["callback_id"] == prompts.QA_REVIEW_NOTE_CALLBACK_ID
    assert view["private_metadata"]
    metadata = json.loads(str(view["private_metadata"]))
    assert metadata["interaction_id"] == "interaction-123"
    assert metadata["channel_id"] == "C123"
    assert metadata["message_ts"] == "1748880000.123456"
    assert metadata["message_text"] == "QA answer text"
    assert "original_blocks" not in metadata
    view_blocks = typing.cast("list[dict[str, object]]", view["blocks"])
    state = typing.cast("dict[str, object]", view_blocks[0]["element"])
    assert state["action_id"] == prompts.QA_REVIEW_NOTE_ACTION_ID
    assert state["initial_value"] == "Existing note"


def test_apply_qa_review_note_save_persists_note_and_returns_small_update_target() -> (
    None
):
    note_store = _RecordingNoteStore()
    body = {
        "view": {
            "private_metadata": json.dumps(
                {
                    "interaction_id": "interaction-123",
                    "channel_id": "C123",
                    "message_ts": "1748880000.123456",
                    "message_text": "QA answer text",
                }
            ),
            "state": _qa_note_view_state("Saved note"),
        }
    }

    result = payloads.apply_qa_review_note_save(
        body=body,
        note_store=note_store,
    )

    assert result is not None
    assert note_store.calls == [("interaction-123", "Saved note")]
    assert result["interaction_id"] == "interaction-123"
    assert result["channel_id"] == "C123"
    assert result["message_ts"] == "1748880000.123456"
    assert result["message_text"] == "QA answer text"


def test_render_note_saved_blocks_preserves_body_and_actions() -> None:
    original_blocks: list[contracts.SlackBlock] = [
        {
            "type": "context",
            "elements": [{"type": "mrkdwn", "text": "QA 1/3 • Case `case-a`"}],
        },
        {"type": "context", "elements": [{"type": "mrkdwn", "text": "❓ QA?"}]},
        {"type": "section", "text": {"type": "mrkdwn", "text": "Answer body"}},
        *blocks.qa_action_blocks("interaction-123"),
    ]

    result_blocks = payloads.render_note_saved_blocks(original_blocks)

    assert "Note saved" in _context_text(result_blocks[0])
    assert result_blocks[1:] == original_blocks[1:]


def test_apply_qa_review_note_save_unknown_id_returns_none() -> None:
    note_store = _RecordingNoteStore(result=False)
    body = {
        "view": {
            "private_metadata": json.dumps(
                {
                    "interaction_id": "missing",
                    "channel_id": "C123",
                    "message_ts": "1748880000.123456",
                }
            ),
            "state": _qa_note_view_state("Saved note"),
        }
    }

    result = payloads.apply_qa_review_note_save(
        body=body,
        note_store=note_store,
    )

    assert result is None
    assert note_store.calls == [("missing", "Saved note")]

"""Tests for the Slack-edge pure Block-Kit constructors."""

from __future__ import annotations

import collections.abc
import typing

import data_assistant.interaction_record as interaction_record
import data_assistant.known_qa_issues as known_qa_issues
import data_assistant.slack.blocks as blocks
import data_assistant.slack.prompts as prompts
import data_assistant.workflow.contracts as contracts


def _button_elements(block: contracts.SlackBlock) -> list[dict[str, object]]:
    """Narrow an ``actions`` block's ``elements`` to a typed list of buttons."""
    elements = block.get("elements")
    assert isinstance(elements, list)
    typed: list[dict[str, object]] = []
    for element in typing.cast("list[object]", elements):
        assert isinstance(element, dict)
        button = typing.cast("dict[str, object]", element)
        typed.append(button)
    return typed


def _action_ids_in(
    block_list: collections.abc.Sequence[contracts.SlackBlock],
) -> set[str]:
    """Collect every button ``action_id`` across all ``actions`` blocks."""
    action_ids: set[str] = set()
    for block in block_list:
        if block.get("type") != "actions":
            continue
        for element in _button_elements(block):
            action_id = element["action_id"]
            assert isinstance(action_id, str)
            action_ids.add(action_id)
    return action_ids


def test_flag_action_blocks_carries_interaction_id_and_action_ids() -> None:
    block_list = blocks.flag_action_blocks("interaction-xyz")

    assert _action_ids_in(block_list) == {
        prompts.FLAG_CORRECTNESS_ACTION_ID,
        prompts.FLAG_FORMATTING_ACTION_ID,
        prompts.FLAG_INVESTIGATE_ACTION_ID,
    }
    # Every button carries the interaction id in its ``value`` so the handler
    # can flag the right record.
    for block in block_list:
        if block.get("type") != "actions":
            continue
        for element in _button_elements(block):
            assert element["value"] == "interaction-xyz"


def test_flag_action_blocks_marks_selected_category_without_status_block() -> None:
    block_list = blocks.flag_action_blocks(
        "interaction-xyz",
        selected_categories=("correctness",),
    )

    assert len(block_list) == 1
    button_by_action_id = {
        typing.cast("str", element["action_id"]): element
        for element in _button_elements(block_list[0])
    }
    assert button_by_action_id[prompts.FLAG_CORRECTNESS_ACTION_ID]["text"] == {
        "type": "plain_text",
        "text": "✓ Incorrect",
    }
    assert button_by_action_id[prompts.FLAG_CORRECTNESS_ACTION_ID]["style"] == "danger"
    assert "style" not in button_by_action_id[prompts.FLAG_FORMATTING_ACTION_ID]
    assert all(block.get("block_id") != "flag_status" for block in block_list)


def test_reply_blocks_in_qa_mode_preselect_known_issue_categories() -> None:
    reply_blocks = blocks.reply_blocks(
        question="What broke?",
        response_blocks=(
            {"type": "section", "text": {"type": "mrkdwn", "text": "Answer body"}},
        ),
        interaction_id="interaction-xyz",
        qa_review_context=interaction_record.QAReviewContext(
            battery_path="docs/qa-retail-questions.md",
            qa_case_id="case-a",
            known_issues=(
                known_qa_issues.KnownQAIssue(
                    issue_number=166,
                    flag_category="correctness",
                ),
            ),
        ),
    )

    actions_block = next(
        block for block in reply_blocks if block.get("type") == "actions"
    )
    button_by_action_id = {
        typing.cast("str", element["action_id"]): element
        for element in _button_elements(actions_block)
    }
    assert button_by_action_id[prompts.FLAG_CORRECTNESS_ACTION_ID]["text"] == {
        "type": "plain_text",
        "text": "✓ Incorrect",
    }
    assert button_by_action_id[prompts.FLAG_CORRECTNESS_ACTION_ID]["style"] == "danger"
    assert button_by_action_id[prompts.FLAG_FORMATTING_ACTION_ID]["text"] == {
        "type": "plain_text",
        "text": "🎨 Formatting",
    }


def test_qa_action_blocks_include_done_but_flag_blocks_do_not() -> None:
    qa_action_ids = _action_ids_in(blocks.qa_action_blocks("interaction-xyz"))
    flag_action_ids = _action_ids_in(blocks.flag_action_blocks("interaction-xyz"))

    assert prompts.QA_DONE_ACTION_ID in qa_action_ids
    assert prompts.QA_DONE_ACTION_ID not in flag_action_ids
    assert prompts.QA_ADD_NOTE_ACTION_ID in qa_action_ids
    assert prompts.QA_ADD_NOTE_ACTION_ID not in flag_action_ids

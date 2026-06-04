"""Tests for the Slack-edge pure Block-Kit constructors."""

from __future__ import annotations

import collections.abc
import typing

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


def test_qa_action_blocks_include_done_but_flag_blocks_do_not() -> None:
    qa_action_ids = _action_ids_in(blocks.qa_action_blocks("interaction-xyz"))
    flag_action_ids = _action_ids_in(blocks.flag_action_blocks("interaction-xyz"))

    assert prompts.QA_DONE_ACTION_ID in qa_action_ids
    assert prompts.QA_DONE_ACTION_ID not in flag_action_ids
    assert prompts.QA_ADD_NOTE_ACTION_ID in qa_action_ids
    assert prompts.QA_ADD_NOTE_ACTION_ID not in flag_action_ids

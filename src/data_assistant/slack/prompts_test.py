"""Tests for the Slack-edge prompts module: vocabulary + triage-flag mirror."""

from __future__ import annotations

import json
import logging
import pathlib

import pytest

import data_assistant.interaction_log as interaction_log
import data_assistant.slack.prompts as prompts


def test_action_id_to_category_is_single_source_of_truth() -> None:
    assert prompts.ACTION_ID_TO_CATEGORY == {
        prompts.FLAG_CORRECTNESS_ACTION_ID: "correctness",
        prompts.FLAG_FORMATTING_ACTION_ID: "formatting",
        prompts.FLAG_INVESTIGATE_ACTION_ID: "investigate",
    }
    # The mapped categories are exactly the Interaction Log flag vocabulary.
    assert set(prompts.ACTION_ID_TO_CATEGORY.values()) == set(
        interaction_log.FLAG_VOCABULARY
    )


def test_flag_interaction_for_triage_logs_updated_record(
    caplog: pytest.LogCaptureFixture,
    tmp_path: pathlib.Path,
) -> None:
    log_path = tmp_path / "interactions.jsonl"
    record: dict[str, object] = {
        "id": "abc123",
        "timestamp": "2026-06-01T12:00:00+00:00",
        "user": "U123",
        "question": "What was revenue by region?",
        "latency_ms": 42,
        "outcome": "answer",
        "response_text": "answer",
        "model": "gpt-4o-mini",
        "flags": [],
    }
    interaction_log.append_interaction(record, path=log_path)

    with caplog.at_level(logging.WARNING, logger=prompts.logger.name):
        changed = prompts.flag_interaction_for_triage(
            interaction_id="abc123",
            category="correctness",
            log_path=log_path,
        )

    assert changed is True
    messages = [
        message
        for message in caplog.messages
        if message.startswith(prompts.FLAGGED_INTERACTION_LOG_PREFIX)
    ]
    assert len(messages) == 1
    payload = messages[0][len(prompts.FLAGGED_INTERACTION_LOG_PREFIX) :]
    mirrored_record = json.loads(payload)
    assert mirrored_record == {**record, "flags": ["correctness"]}


def test_flag_interaction_for_triage_unknown_id_logs_nothing(
    caplog: pytest.LogCaptureFixture,
    tmp_path: pathlib.Path,
) -> None:
    log_path = tmp_path / "interactions.jsonl"
    interaction_log.append_interaction(
        {
            "id": "abc123",
            "timestamp": "2026-06-01T12:00:00+00:00",
            "user": "U123",
            "question": "What was revenue by region?",
            "latency_ms": 42,
            "outcome": "answer",
            "response_text": "answer",
            "model": "gpt-4o-mini",
            "flags": [],
        },
        path=log_path,
    )

    with caplog.at_level(logging.WARNING, logger=prompts.logger.name):
        changed = prompts.flag_interaction_for_triage(
            interaction_id="missing",
            category="correctness",
            log_path=log_path,
        )

    assert changed is False
    assert not any(
        message.startswith(prompts.FLAGGED_INTERACTION_LOG_PREFIX)
        for message in caplog.messages
    )


def test_toggle_interaction_flag_for_triage_logs_unflagged_record(
    caplog: pytest.LogCaptureFixture,
    tmp_path: pathlib.Path,
) -> None:
    log_path = tmp_path / "interactions.jsonl"
    record: dict[str, object] = {
        "id": "abc123",
        "timestamp": "2026-06-01T12:00:00+00:00",
        "user": "U123",
        "question": "What was revenue by region?",
        "latency_ms": 42,
        "outcome": "answer",
        "response_text": "answer",
        "model": "gpt-4o-mini",
        "flags": ["correctness"],
    }
    interaction_log.append_interaction(record, path=log_path)

    with caplog.at_level(logging.WARNING, logger=prompts.logger.name):
        result = prompts.toggle_interaction_flag_for_triage(
            interaction_id="abc123",
            category="correctness",
            log_path=log_path,
        )

    assert result is interaction_log.ToggleFlagResult.UNSELECTED
    messages = [
        message
        for message in caplog.messages
        if message.startswith(prompts.FLAGGED_INTERACTION_LOG_PREFIX)
    ]
    assert len(messages) == 1
    payload = messages[0][len(prompts.FLAGGED_INTERACTION_LOG_PREFIX) :]
    mirrored_record = json.loads(payload)
    assert mirrored_record == {**record, "flags": []}

"""Tests for the local Interaction Log (append-only JSONL, dev consumer).

The Interaction Log is the local-dev Decision Trail consumer (see ADR-0016): a
maintainer pastes a logged interaction into Claude Code when asking for an
improvement. These tests exercise file I/O against ``tmp_path`` only and never
touch the canonical ``logs/interactions.jsonl``.
"""

from __future__ import annotations

import json
import pathlib

import data_assistant.interaction_log as interaction_log


def _record(**overrides: object) -> dict[str, object]:
    record: dict[str, object] = {
        "id": "abc123",
        "timestamp": "2026-06-01T12:00:00+00:00",
        "user": "U123",
        "question": "What was total revenue by region in January 2026?",
        "latency_ms": 42,
        "outcome": "answer",
        "response_text": "Total revenue ...",
        "model": "gpt-4o-mini",
        "flags": [],
    }
    record.update(overrides)
    return record


def test_append_interaction_writes_one_json_line(tmp_path: pathlib.Path) -> None:
    log_path = tmp_path / "interactions.jsonl"
    record = _record()

    returned_id = interaction_log.append_interaction(record, path=log_path)

    assert returned_id == "abc123"
    lines = log_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0]) == record


def test_append_interaction_appends_second_line(tmp_path: pathlib.Path) -> None:
    log_path = tmp_path / "interactions.jsonl"

    interaction_log.append_interaction(_record(id="first"), path=log_path)
    interaction_log.append_interaction(_record(id="second"), path=log_path)

    lines = log_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["id"] == "first"
    assert json.loads(lines[1])["id"] == "second"


def test_append_interaction_creates_parent_directory(tmp_path: pathlib.Path) -> None:
    log_path = tmp_path / "nested" / "logs" / "interactions.jsonl"

    interaction_log.append_interaction(_record(), path=log_path)

    assert log_path.exists()


def test_append_interaction_round_trips_via_json(tmp_path: pathlib.Path) -> None:
    log_path = tmp_path / "interactions.jsonl"
    record = _record(flags=[])

    interaction_log.append_interaction(record, path=log_path)

    loaded = json.loads(log_path.read_text(encoding="utf-8"))
    assert loaded == record
    assert loaded["flags"] == []


def test_flag_vocabulary_constant_is_correctness_and_formatting() -> None:
    assert set(interaction_log.FLAG_VOCABULARY) == {"correctness", "formatting"}


def test_default_log_path_is_repo_root_logs_interactions_jsonl() -> None:
    assert interaction_log.DEFAULT_LOG_PATH.name == "interactions.jsonl"
    assert interaction_log.DEFAULT_LOG_PATH.parent.name == "logs"

"""Tests for the clear_flags operator script."""

from __future__ import annotations

import pathlib

from data_assistant import interaction_log
from scripts import clear_flags


def _record(**overrides: object) -> dict[str, object]:
    record: dict[str, object] = {
        "id": "abc123",
        "timestamp": "2026-06-01T12:00:00+00:00",
        "user": "U123",
        "question": "What was total revenue?",
        "latency_ms": 42,
        "outcome": "answer",
        "response_text": "Total revenue ...",
        "model": "gpt-4o-mini",
        "flags": [],
    }
    record.update(overrides)
    return record


def _log_with_records(tmp_path: pathlib.Path) -> pathlib.Path:
    log_path = tmp_path / "interactions.jsonl"
    interaction_log.append_interaction(
        _record(id="flagged", flags=["correctness"]), path=log_path
    )
    interaction_log.append_interaction(_record(id="clean", flags=[]), path=log_path)
    return log_path


def test_clears_flagged_record_and_reports_per_id(
    tmp_path: pathlib.Path, capsys: object
) -> None:
    log_path = _log_with_records(tmp_path)

    exit_code = clear_flags.main(
        ["flagged", "clean", "missing", "--log-path", str(log_path)]
    )

    assert exit_code == 0
    out = capsys.readouterr().out  # type: ignore[attr-defined]
    assert out == "flagged\tTrue\nclean\tFalse\nmissing\tFalse\n"
    assert interaction_log.find_interaction("flagged", path=log_path) == {
        **_record(id="flagged"),
        "flags": [],
    }

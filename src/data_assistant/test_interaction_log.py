"""Tests for the local Interaction Log (retention-bounded JSONL, dev consumer).

The Interaction Log is the local-dev Decision Trail consumer (see ADR-0016): a
maintainer pastes a logged interaction into Claude Code when asking for an
improvement. These tests exercise file I/O against ``tmp_path`` only and never
touch the canonical ``logs/interactions.jsonl``.
"""

from __future__ import annotations

import json
import pathlib

import pytest

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


def _line(record: dict[str, object]) -> str:
    return json.dumps(record)


def _line_bytes(line: str) -> int:
    return len(line.encode("utf-8")) + 1


def _write_lines(path: pathlib.Path, lines: list[str]) -> None:
    path.write_text("".join(f"{line}\n" for line in lines), encoding="utf-8")


def _read_lines(path: pathlib.Path) -> list[str]:
    return path.read_text(encoding="utf-8").splitlines()


def _read_json_records(path: pathlib.Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in _read_lines(path)]


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


def test_find_interaction_returns_retained_record_by_id(tmp_path: pathlib.Path) -> None:
    log_path = tmp_path / "interactions.jsonl"
    first = _record(id="first")
    second = _record(id="second", flags=["correctness"])
    interaction_log.append_interaction(first, path=log_path)
    interaction_log.append_interaction(second, path=log_path)

    found = interaction_log.find_interaction("second", path=log_path)

    assert found == second


def test_find_interaction_missing_id_returns_none(tmp_path: pathlib.Path) -> None:
    log_path = tmp_path / "interactions.jsonl"
    interaction_log.append_interaction(_record(id="first"), path=log_path)

    assert interaction_log.find_interaction("missing", path=log_path) is None


def test_find_interaction_missing_file_returns_none(tmp_path: pathlib.Path) -> None:
    assert (
        interaction_log.find_interaction("abc123", path=tmp_path / "missing.jsonl")
        is None
    )


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


def test_flag_vocabulary_constant_is_correctness_formatting_investigate() -> None:
    assert set(interaction_log.FLAG_VOCABULARY) == {
        "correctness",
        "formatting",
        "investigate",
    }


def test_default_log_path_is_repo_root_logs_interactions_jsonl() -> None:
    assert interaction_log.DEFAULT_LOG_PATH.name == "interactions.jsonl"
    assert interaction_log.DEFAULT_LOG_PATH.parent.name == "logs"


# --- Interaction Log Retention Policy ---------------------------------------


def test_append_interaction_does_not_compact_before_trigger(
    tmp_path: pathlib.Path,
) -> None:
    log_path = tmp_path / "interactions.jsonl"
    for index in range(3):
        interaction_log.append_interaction(
            _record(id=f"answer-{index}"),
            path=log_path,
            retention_policy=interaction_log.RetentionPolicy(
                trigger_bytes=10_000,
                target_bytes=1,
                recent_unflagged_answer_limit=1,
            ),
        )

    assert [record["id"] for record in _read_json_records(log_path)] == [
        "answer-0",
        "answer-1",
        "answer-2",
    ]


def test_append_interaction_compacts_by_priority_then_keeps_chronological_order(
    tmp_path: pathlib.Path,
) -> None:
    log_path = tmp_path / "interactions.jsonl"
    retained_lines = [
        _line(_record(id="flagged", flags=["legacy-category"])),
        _line(_record(id="error", outcome="error")),
        "not-json",
        _line(_record(id="non-answer", outcome="non_answer")),
    ]
    all_lines = [
        _line(_record(id="old-answer")),
        *retained_lines,
        _line(_record(id="recent-answer")),
    ]
    _write_lines(log_path, all_lines)

    interaction_log.append_interaction(
        _record(id="new-answer"),
        path=log_path,
        retention_policy=interaction_log.RetentionPolicy(
            trigger_bytes=1,
            target_bytes=sum(_line_bytes(line) for line in retained_lines),
            recent_unflagged_answer_limit=5,
        ),
    )

    assert _read_lines(log_path) == retained_lines


def test_append_interaction_retention_limits_recent_unflagged_answers(
    tmp_path: pathlib.Path,
) -> None:
    log_path = tmp_path / "interactions.jsonl"
    _write_lines(
        log_path,
        [
            _line(_record(id="answer-1")),
            _line(_record(id="answer-2")),
            _line(_record(id="answer-3")),
        ],
    )

    interaction_log.append_interaction(
        _record(id="answer-4"),
        path=log_path,
        retention_policy=interaction_log.RetentionPolicy(
            trigger_bytes=1,
            target_bytes=10_000,
            recent_unflagged_answer_limit=2,
        ),
    )

    assert [record["id"] for record in _read_json_records(log_path)] == [
        "answer-3",
        "answer-4",
    ]


def test_flag_interaction_promotes_record_before_retention(
    tmp_path: pathlib.Path,
) -> None:
    log_path = tmp_path / "interactions.jsonl"
    flag_target = _record(id="flag-target")
    _write_lines(
        log_path,
        [
            _line(flag_target),
            _line(_record(id="newer-answer")),
        ],
    )
    flagged_line = _line({**flag_target, "flags": ["correctness"]})

    changed = interaction_log.flag_interaction(
        "flag-target",
        "correctness",
        path=log_path,
        retention_policy=interaction_log.RetentionPolicy(
            trigger_bytes=1,
            target_bytes=_line_bytes(flagged_line),
            recent_unflagged_answer_limit=5,
        ),
    )

    assert changed is True
    assert _read_json_records(log_path) == [{**flag_target, "flags": ["correctness"]}]


def test_retention_keeps_one_line_when_one_line_exceeds_target(
    tmp_path: pathlib.Path,
) -> None:
    log_path = tmp_path / "interactions.jsonl"
    large_record = _record(id="large", response_text="x" * 200)
    interaction_log.append_interaction(
        large_record,
        path=log_path,
        retention_policy=interaction_log.RetentionPolicy(
            trigger_bytes=1,
            target_bytes=1,
            recent_unflagged_answer_limit=5,
        ),
    )

    assert [record["id"] for record in _read_json_records(log_path)] == ["large"]


# --- flag_interaction (Slice 2, issue #111) ---------------------------------


def _seed_log(tmp_path: pathlib.Path, *records: dict[str, object]) -> pathlib.Path:
    log_path = tmp_path / "interactions.jsonl"
    for record in records:
        interaction_log.append_interaction(record, path=log_path)
    return log_path


def test_flag_interaction_appends_category_to_matching_record(
    tmp_path: pathlib.Path,
) -> None:
    log_path = _seed_log(tmp_path, _record(id="abc123", flags=[]))

    changed = interaction_log.flag_interaction("abc123", "correctness", path=log_path)

    assert changed is True
    records = [
        json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()
    ]
    assert len(records) == 1
    assert records[0]["flags"] == ["correctness"]


def test_flag_interaction_dedupes_same_category(tmp_path: pathlib.Path) -> None:
    log_path = _seed_log(tmp_path, _record(id="abc123", flags=[]))

    interaction_log.flag_interaction("abc123", "correctness", path=log_path)
    changed = interaction_log.flag_interaction("abc123", "correctness", path=log_path)

    assert changed is True
    records = [
        json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()
    ]
    assert records[0]["flags"] == ["correctness"]


def test_flag_interaction_keeps_both_categories_on_one_record(
    tmp_path: pathlib.Path,
) -> None:
    log_path = _seed_log(tmp_path, _record(id="abc123", flags=[]))

    interaction_log.flag_interaction("abc123", "correctness", path=log_path)
    interaction_log.flag_interaction("abc123", "formatting", path=log_path)

    records = [
        json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()
    ]
    assert set(records[0]["flags"]) == {"correctness", "formatting"}


def test_flag_interaction_appends_investigate_category(
    tmp_path: pathlib.Path,
) -> None:
    log_path = _seed_log(tmp_path, _record(id="abc123", flags=[]))

    changed = interaction_log.flag_interaction("abc123", "investigate", path=log_path)

    assert changed is True
    records = [
        json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()
    ]
    assert records[0]["flags"] == ["investigate"]


def test_flag_interaction_only_touches_matching_record(
    tmp_path: pathlib.Path,
) -> None:
    log_path = _seed_log(
        tmp_path,
        _record(id="first", flags=[]),
        _record(id="second", flags=[]),
    )

    interaction_log.flag_interaction("second", "formatting", path=log_path)

    records = [
        json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()
    ]
    assert records[0]["id"] == "first"
    assert records[0]["flags"] == []
    assert records[1]["id"] == "second"
    assert records[1]["flags"] == ["formatting"]


def test_flag_interaction_unknown_id_is_noop_returns_false(
    tmp_path: pathlib.Path,
) -> None:
    log_path = _seed_log(tmp_path, _record(id="abc123", flags=[]))
    before = log_path.read_text(encoding="utf-8")

    changed = interaction_log.flag_interaction(
        "does-not-exist", "correctness", path=log_path
    )

    assert changed is False
    assert log_path.read_text(encoding="utf-8") == before


def test_flag_interaction_unknown_category_raises_value_error(
    tmp_path: pathlib.Path,
) -> None:
    log_path = _seed_log(tmp_path, _record(id="abc123", flags=[]))

    with pytest.raises(ValueError):
        interaction_log.flag_interaction("abc123", "nonsense", path=log_path)


# --- clear_flags (triage clear-handled, skill follow-up) --------------------


def test_clear_flags_empties_flags_but_keeps_record(tmp_path: pathlib.Path) -> None:
    log_path = _seed_log(tmp_path, _record(id="abc123", flags=["correctness"]))

    cleared = interaction_log.clear_flags("abc123", path=log_path)

    assert cleared is True
    records = [
        json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()
    ]
    # Record survives (still useful corpus); only its flags are emptied.
    assert len(records) == 1
    assert records[0]["id"] == "abc123"
    assert records[0]["flags"] == []


def test_clear_flags_clears_multiple_categories(tmp_path: pathlib.Path) -> None:
    log_path = _seed_log(
        tmp_path, _record(id="abc123", flags=["correctness", "formatting"])
    )

    cleared = interaction_log.clear_flags("abc123", path=log_path)

    assert cleared is True
    records = [
        json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()
    ]
    assert records[0]["flags"] == []


def test_clear_flags_only_touches_matching_record(tmp_path: pathlib.Path) -> None:
    log_path = _seed_log(
        tmp_path,
        _record(id="first", flags=["correctness"]),
        _record(id="second", flags=["formatting"]),
    )

    interaction_log.clear_flags("second", path=log_path)

    records = [
        json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()
    ]
    assert records[0]["flags"] == ["correctness"]
    assert records[1]["flags"] == []


def test_clear_flags_unknown_id_is_noop_returns_false(tmp_path: pathlib.Path) -> None:
    log_path = _seed_log(tmp_path, _record(id="abc123", flags=["correctness"]))
    before = log_path.read_text(encoding="utf-8")

    cleared = interaction_log.clear_flags("does-not-exist", path=log_path)

    assert cleared is False
    assert log_path.read_text(encoding="utf-8") == before


def test_clear_flags_already_unflagged_is_noop_returns_false(
    tmp_path: pathlib.Path,
) -> None:
    log_path = _seed_log(tmp_path, _record(id="abc123", flags=[]))
    before = log_path.read_text(encoding="utf-8")

    cleared = interaction_log.clear_flags("abc123", path=log_path)

    # Nothing to clear -> no rewrite, returns False.
    assert cleared is False
    assert log_path.read_text(encoding="utf-8") == before


def test_clear_flags_missing_file_returns_false(tmp_path: pathlib.Path) -> None:
    cleared = interaction_log.clear_flags("abc123", path=tmp_path / "nope.jsonl")

    assert cleared is False

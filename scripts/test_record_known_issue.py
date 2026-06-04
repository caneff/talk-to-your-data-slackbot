"""Tests for the record_known_issue operator script."""

from __future__ import annotations

import pathlib

from data_assistant import known_qa_issues
from scripts import record_known_issue


def _battery(tmp_path: pathlib.Path) -> pathlib.Path:
    battery_path = tmp_path / "battery.md"
    battery_path.write_text("- [case-1] What was revenue?\n", encoding="utf-8")
    return battery_path


def test_records_eligible_mapping(tmp_path: pathlib.Path) -> None:
    battery_path = _battery(tmp_path)

    exit_code = record_known_issue.main(
        [
            "--qa-case-id",
            "case-1",
            "--issue-number",
            "42",
            "--flag-category",
            "correctness",
            "--battery-path",
            str(battery_path),
        ]
    )

    assert exit_code == 0
    sidecar_path = known_qa_issues.default_sidecar_path(battery_path)
    sidecar = known_qa_issues.load_sidecar(sidecar_path, valid_case_ids=["case-1"])
    issues = sidecar.questions["case-1"]
    assert [(issue.issue_number, issue.flag_category) for issue in issues] == [
        (42, "correctness")
    ]


def test_unknown_case_id_is_a_noop(tmp_path: pathlib.Path) -> None:
    battery_path = _battery(tmp_path)

    exit_code = record_known_issue.main(
        [
            "--qa-case-id",
            "nope",
            "--issue-number",
            "42",
            "--flag-category",
            "correctness",
            "--battery-path",
            str(battery_path),
        ]
    )

    assert exit_code == 1
    assert not known_qa_issues.default_sidecar_path(battery_path).exists()

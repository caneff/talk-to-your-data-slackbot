"""Tests for the Known QA Issue preflight subsystem.

These exercise sidecar create/validate/prune/rewrite behavior with an injected
``is_issue_open`` -- no live ``gh`` call.
"""

from __future__ import annotations

import pathlib

import pytest

import data_assistant.known_qa_issues as known_qa_issues
import data_assistant.qa_battery as qa_battery
import data_assistant.qa_preflight as qa_preflight


def test_resolve_known_issues_path_honors_override() -> None:
    battery_path = pathlib.Path("docs/qa-retail-questions.md")
    override_path = pathlib.Path("docs/custom-known-issues.json")

    assert (
        qa_preflight.resolve_known_issues_path(
            battery_path=battery_path,
            known_issues_path=override_path,
        )
        == override_path
    )


def test_preflight_known_issues_skips_escape_hatch_unidentified_cases(
    tmp_path: pathlib.Path,
) -> None:
    sidecar_path = _sidecar_path(tmp_path)

    qa_preflight.preflight_known_issues(
        battery_path=tmp_path / "qa-retail-questions.md",
        cases=[qa_battery.QACase(id=None, question="legacy question")],
        known_issues_path=sidecar_path,
        skip_prune=False,
        is_issue_open=lambda _issue_number: True,
    )

    assert not sidecar_path.exists()


def test_preflight_known_issues_rejects_mixed_identified_and_unidentified_cases(
    tmp_path: pathlib.Path,
) -> None:
    sidecar_path = _sidecar_path(tmp_path)

    with pytest.raises(ValueError, match="Mixed identified and unidentified QA cases"):
        qa_preflight.preflight_known_issues(
            battery_path=tmp_path / "qa-retail-questions.md",
            cases=[_case("case-a"), qa_battery.QACase(id=None, question="legacy")],
            known_issues_path=sidecar_path,
            skip_prune=False,
            is_issue_open=lambda _issue_number: True,
        )

    assert not sidecar_path.exists()


def test_preflight_known_issues_aborts_when_prune_fails(
    tmp_path: pathlib.Path,
) -> None:
    sidecar_path = _sidecar_path(tmp_path)
    _write_sidecar(
        sidecar_path,
        {
            "case-a": [
                known_qa_issues.KnownQAIssue(
                    issue_number=165,
                    flag_category="correctness",
                )
            ]
        },
    )

    def fail_lookup(_issue_number: int) -> bool:
        raise RuntimeError("lookup failed")

    original_text = sidecar_path.read_text(encoding="utf-8")

    with pytest.raises(known_qa_issues.KnownQAIssuePruneError, match="lookup failed"):
        qa_preflight.preflight_known_issues(
            battery_path=tmp_path / "qa-retail-questions.md",
            cases=[_case("case-a")],
            known_issues_path=sidecar_path,
            skip_prune=False,
            is_issue_open=fail_lookup,
        )

    assert sidecar_path.read_text(encoding="utf-8") == original_text


def test_preflight_known_issues_skip_prune_keeps_existing_sidecar(
    tmp_path: pathlib.Path,
) -> None:
    sidecar_path = _sidecar_path(tmp_path)
    _write_sidecar(
        sidecar_path,
        {
            "case-a": [
                known_qa_issues.KnownQAIssue(
                    issue_number=165,
                    flag_category="correctness",
                )
            ]
        },
    )

    def fail_lookup(_issue_number: int) -> bool:
        raise RuntimeError("should not be called")

    qa_preflight.preflight_known_issues(
        battery_path=tmp_path / "qa-retail-questions.md",
        cases=[_case("case-a")],
        known_issues_path=sidecar_path,
        skip_prune=True,
        is_issue_open=fail_lookup,
    )

    assert _load_sidecar(sidecar_path, valid_case_ids=["case-a"]).questions == {
        "case-a": [
            known_qa_issues.KnownQAIssue(
                issue_number=165,
                flag_category="correctness",
            )
        ]
    }


def test_preflight_known_issues_prunes_and_rewrites_sidecar(
    tmp_path: pathlib.Path,
) -> None:
    sidecar_path = _sidecar_path(tmp_path)

    qa_preflight.preflight_known_issues(
        battery_path=tmp_path / "qa-retail-questions.md",
        cases=[_case("case-a", question="Question A?"), _case("case-b")],
        known_issues_path=sidecar_path,
        skip_prune=False,
        is_issue_open=lambda issue_number: issue_number == 165,
    )

    assert (
        _load_sidecar(
            sidecar_path,
            valid_case_ids=["case-a", "case-b"],
        ).questions
        == {}
    )


def test_preflight_known_issues_fetches_each_unique_issue_once(
    tmp_path: pathlib.Path,
) -> None:
    sidecar_path = _sidecar_path(tmp_path)
    _write_sidecar(
        sidecar_path,
        {
            "case-a": [
                known_qa_issues.KnownQAIssue(
                    issue_number=165,
                    flag_category="correctness",
                ),
                known_qa_issues.KnownQAIssue(
                    issue_number=166,
                    flag_category="formatting",
                ),
            ],
            "case-b": [
                known_qa_issues.KnownQAIssue(
                    issue_number=165,
                    flag_category="investigate",
                )
            ],
        },
    )
    seen_issue_numbers: list[int] = []

    def is_issue_open(issue_number: int) -> bool:
        seen_issue_numbers.append(issue_number)
        return issue_number == 165

    qa_preflight.preflight_known_issues(
        battery_path=tmp_path / "qa-retail-questions.md",
        cases=[_case("case-a"), _case("case-b")],
        known_issues_path=sidecar_path,
        skip_prune=False,
        is_issue_open=is_issue_open,
    )

    assert seen_issue_numbers == [165, 166]
    assert _load_sidecar(sidecar_path, valid_case_ids=["case-a", "case-b"]) == (
        known_qa_issues.KnownQAIssueSidecar(
            version=1,
            questions={
                "case-a": [
                    known_qa_issues.KnownQAIssue(
                        issue_number=165,
                        flag_category="correctness",
                    )
                ],
                "case-b": [
                    known_qa_issues.KnownQAIssue(
                        issue_number=165,
                        flag_category="investigate",
                    )
                ],
            },
        )
    )


def _sidecar_path(tmp_path: pathlib.Path) -> pathlib.Path:
    return tmp_path / "qa-retail-questions.known-issues.json"


def _case(case_id: str, *, question: str = "Question?") -> qa_battery.QACase:
    return qa_battery.QACase(id=case_id, question=question)


def _write_sidecar(
    path: pathlib.Path,
    questions: dict[str, list[known_qa_issues.KnownQAIssue]],
) -> None:
    known_qa_issues.write_sidecar(
        path,
        known_qa_issues.KnownQAIssueSidecar(version=1, questions=questions),
    )


def _load_sidecar(
    path: pathlib.Path,
    *,
    valid_case_ids: list[str],
) -> known_qa_issues.KnownQAIssueSidecar:
    return known_qa_issues.load_sidecar(path, valid_case_ids=valid_case_ids)

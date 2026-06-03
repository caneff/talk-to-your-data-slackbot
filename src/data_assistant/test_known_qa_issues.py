from __future__ import annotations

import pathlib
import textwrap

import pytest

import data_assistant.interaction_log as interaction_log
import data_assistant.known_qa_issues as known_qa_issues


def test_default_sidecar_path_replaces_battery_suffix() -> None:
    battery_path = pathlib.Path("docs/qa-retail-questions.md")

    assert known_qa_issues.default_sidecar_path(battery_path) == pathlib.Path(
        "docs/qa-retail-questions.known-issues.json"
    )


def test_load_sidecar_creates_empty_version_one_file_for_missing_strict_battery(
    tmp_path: pathlib.Path,
) -> None:
    sidecar_path = tmp_path / "qa-retail-questions.known-issues.json"

    sidecar = known_qa_issues.load_sidecar(
        sidecar_path,
        valid_case_ids=["case-b", "case-a"],
        create_if_missing=True,
    )

    assert sidecar == known_qa_issues.KnownQAIssueSidecar(version=1, questions={})
    assert sidecar_path.read_text(encoding="utf-8") == (
        '{\n  "version": 1,\n  "questions": {}\n}\n'
    )


def test_load_sidecar_rejects_unknown_future_version(tmp_path: pathlib.Path) -> None:
    sidecar_path = tmp_path / "qa-retail-questions.known-issues.json"
    sidecar_path.write_text(
        textwrap.dedent(
            """\
            {
              "version": 2,
              "questions": {}
            }
            """
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Unsupported Known QA Issue sidecar version"):
        known_qa_issues.load_sidecar(
            sidecar_path,
            valid_case_ids=["case-a"],
        )


def test_load_sidecar_rejects_unknown_question_keys(tmp_path: pathlib.Path) -> None:
    sidecar_path = tmp_path / "qa-retail-questions.known-issues.json"
    sidecar_path.write_text(
        textwrap.dedent(
            """\
            {
              "version": 1,
              "questions": {
                "missing-case": [
                  {
                    "issue_number": 165,
                    "flag_category": "correctness"
                  }
                ]
              }
            }
            """
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Unknown QA case id in sidecar: missing-case"):
        known_qa_issues.load_sidecar(
            sidecar_path,
            valid_case_ids=["case-a"],
        )


def test_load_sidecar_rejects_invalid_issue_numbers_and_flag_categories(
    tmp_path: pathlib.Path,
) -> None:
    sidecar_path = tmp_path / "qa-retail-questions.known-issues.json"
    sidecar_path.write_text(
        textwrap.dedent(
            """\
            {
              "version": 1,
              "questions": {
                "case-a": [
                  {
                    "issue_number": 0,
                    "flag_category": "correctness"
                  },
                  {
                    "issue_number": 165,
                    "flag_category": "not-a-real-category"
                  }
                ]
              }
            }
            """
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="issue_number"):
        known_qa_issues.load_sidecar(
            sidecar_path,
            valid_case_ids=["case-a"],
        )


def test_prune_sidecar_removes_closed_and_missing_cases_and_empty_question_keys() -> (
    None
):
    sidecar = known_qa_issues.KnownQAIssueSidecar(
        version=1,
        questions={
            "case-a": [
                known_qa_issues.KnownQAIssue(
                    issue_number=165, flag_category="correctness"
                ),
                known_qa_issues.KnownQAIssue(
                    issue_number=166, flag_category="formatting"
                ),
            ],
            "missing-case": [
                known_qa_issues.KnownQAIssue(
                    issue_number=167, flag_category="investigate"
                )
            ],
            "case-empty": [
                known_qa_issues.KnownQAIssue(
                    issue_number=168, flag_category="correctness"
                )
            ],
        },
    )

    pruned = known_qa_issues.prune_sidecar(
        sidecar,
        valid_case_ids=["case-a", "case-empty"],
        is_issue_open=_is_only_issue_165_open,
    )

    assert pruned == known_qa_issues.KnownQAIssueSidecar(
        version=1,
        questions={
            "case-a": [
                known_qa_issues.KnownQAIssue(
                    issue_number=165,
                    flag_category="correctness",
                )
            ]
        },
    )


def test_prune_sidecar_surfaces_issue_lookup_failures() -> None:
    sidecar = known_qa_issues.KnownQAIssueSidecar(
        version=1,
        questions={
            "case-a": [
                known_qa_issues.KnownQAIssue(
                    issue_number=165, flag_category="correctness"
                )
            ]
        },
    )

    def boom(_issue_number: int) -> bool:
        raise RuntimeError("gh failed")

    with pytest.raises(known_qa_issues.KnownQAIssuePruneError, match="gh failed"):
        known_qa_issues.prune_sidecar(
            sidecar,
            valid_case_ids=["case-a"],
            is_issue_open=boom,
        )


def test_serialize_sidecar_is_deterministic() -> None:
    sidecar = known_qa_issues.KnownQAIssueSidecar(
        version=1,
        questions={
            "case-b": [
                known_qa_issues.KnownQAIssue(
                    issue_number=200, flag_category="investigate"
                ),
                known_qa_issues.KnownQAIssue(
                    issue_number=199, flag_category="correctness"
                ),
            ],
            "case-a": [
                known_qa_issues.KnownQAIssue(
                    issue_number=201, flag_category="formatting"
                )
            ],
        },
    )

    assert known_qa_issues.serialize_sidecar(sidecar) == textwrap.dedent(
        """\
        {
          "version": 1,
          "questions": {
            "case-a": [
              {
                "issue_number": 201,
                "flag_category": "formatting"
              }
            ],
            "case-b": [
              {
                "issue_number": 199,
                "flag_category": "correctness"
              },
              {
                "issue_number": 200,
                "flag_category": "investigate"
              }
            ]
          }
        }
        """
    )


def test_valid_flag_categories_match_interaction_log_vocabulary() -> None:
    assert known_qa_issues.VALID_FLAG_CATEGORIES == interaction_log.FLAG_VOCABULARY


def _is_only_issue_165_open(issue_number: int) -> bool:
    return issue_number in {165}

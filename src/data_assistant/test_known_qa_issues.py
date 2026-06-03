from __future__ import annotations

import json
import pathlib
import textwrap
import typing

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

    assert sidecar == _sidecar({})
    assert known_qa_issues.load_sidecar(
        sidecar_path,
        valid_case_ids=["case-a", "case-b"],
    ) == _sidecar({})


@pytest.mark.parametrize(
    ("payload", "valid_case_ids", "match"),
    [
        pytest.param(
            {
                "version": 2,
                "questions": {},
            },
            ["case-a"],
            "Unsupported Known QA Issue sidecar version",
            id="future-version",
        ),
        pytest.param(
            {
                "version": 1,
                "questions": {},
                "notes": "secret",
            },
            ["case-a"],
            "Unknown top-level field",
            id="unknown-top-level-field",
        ),
        pytest.param(
            {
                "version": 1,
                "questions": {
                    "missing-case": [
                        {
                            "issue_number": 165,
                            "flag_category": "correctness",
                        }
                    ]
                },
            },
            ["case-a"],
            "Unknown QA case id in sidecar: missing-case",
            id="unknown-qa-case-id",
        ),
        pytest.param(
            {
                "version": 1,
                "questions": {
                    "case-a": [
                        {
                            "issue_number": 0,
                            "flag_category": "correctness",
                        }
                    ]
                },
            },
            ["case-a"],
            "issue_number",
            id="invalid-issue-number",
        ),
        pytest.param(
            {
                "version": 1,
                "questions": {
                    "case-a": [
                        {
                            "issue_number": 165,
                            "flag_category": "not-a-real-category",
                        }
                    ]
                },
            },
            ["case-a"],
            "flag_category",
            id="invalid-flag-category",
        ),
        pytest.param(
            {
                "version": 1,
                "questions": {
                    "case-a": [
                        {
                            "issue_number": 165,
                            "flag_category": "correctness",
                            "response_text": "leak",
                        }
                    ]
                },
            },
            ["case-a"],
            "Unknown entry field",
            id="unknown-entry-field",
        ),
    ],
)
def test_load_sidecar_rejects_malformed_payloads(
    tmp_path: pathlib.Path,
    payload: dict[str, object],
    valid_case_ids: list[str],
    match: str,
) -> None:
    sidecar_path = tmp_path / "qa-retail-questions.known-issues.json"
    _write_payload(sidecar_path, payload)

    with pytest.raises(ValueError, match=match):
        known_qa_issues.load_sidecar(
            sidecar_path,
            valid_case_ids=valid_case_ids,
        )


def test_load_sidecar_rejects_non_object_payload(tmp_path: pathlib.Path) -> None:
    sidecar_path = tmp_path / "qa-retail-questions.known-issues.json"
    sidecar_path.write_text(
        json.dumps(["not", "an", "object"]),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="top-level JSON object required"):
        known_qa_issues.load_sidecar(
            sidecar_path,
            valid_case_ids=["case-a"],
        )


def test_prune_sidecar_removes_closed_and_missing_cases_and_empty_question_keys() -> (
    None
):
    sidecar = _sidecar(
        {
            "case-a": [_issue(165), _issue(166, "formatting")],
            "missing-case": [_issue(167, "investigate")],
            "case-empty": [_issue(168)],
        }
    )

    pruned = known_qa_issues.prune_sidecar(
        sidecar,
        valid_case_ids=["case-a", "case-empty"],
        is_issue_open=_is_only_issue_165_open,
    )

    assert pruned == _sidecar({"case-a": [_issue(165)]})


def test_prune_sidecar_surfaces_issue_lookup_failures() -> None:
    sidecar = _sidecar({"case-a": [_issue(165)]})

    def boom(_issue_number: int) -> bool:
        raise RuntimeError("gh failed")

    with pytest.raises(known_qa_issues.KnownQAIssuePruneError, match="gh failed"):
        known_qa_issues.prune_sidecar(
            sidecar,
            valid_case_ids=["case-a"],
            is_issue_open=boom,
        )


def test_serialize_sidecar_is_deterministic() -> None:
    sidecar = _sidecar(
        {
            "case-b": [_issue(200, "investigate"), _issue(199)],
            "case-a": [_issue(201, "formatting")],
        }
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


def _issue(
    issue_number: int,
    flag_category: str = "correctness",
) -> known_qa_issues.KnownQAIssue:
    return known_qa_issues.KnownQAIssue(
        issue_number=issue_number,
        flag_category=flag_category,
    )


def _sidecar(
    questions: dict[str, list[known_qa_issues.KnownQAIssue]],
) -> known_qa_issues.KnownQAIssueSidecar:
    return known_qa_issues.KnownQAIssueSidecar(version=1, questions=questions)


def _write_payload(path: pathlib.Path, payload: typing.Mapping[str, object]) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")

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


def test_load_sidecar_returns_empty_version_one_sidecar_for_missing_file(
    tmp_path: pathlib.Path,
) -> None:
    sidecar_path = tmp_path / "qa-retail-questions.known-issues.json"

    sidecar = known_qa_issues.load_sidecar(
        sidecar_path,
        valid_case_ids=["case-b", "case-a"],
        create_if_missing=True,
    )

    assert sidecar == _sidecar({})
    assert not sidecar_path.exists()


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


def test_prune_sidecar_using_open_issue_numbers_is_pure_transform() -> None:
    sidecar = _sidecar(
        {
            "case-a": [_issue(165), _issue(166, "formatting")],
            "missing-case": [_issue(167, "investigate")],
            "case-empty": [_issue(168)],
        }
    )

    pruned = known_qa_issues.prune_sidecar_using_open_issue_numbers(
        sidecar,
        valid_case_ids=["case-a", "case-empty"],
        open_issue_numbers={165},
    )

    assert pruned == _sidecar({"case-a": [_issue(165)]})


def test_record_known_issue_adds_new_entry() -> None:
    updated = known_qa_issues.record_known_issue(
        _sidecar({}),
        qa_case_id="case-a",
        issue_number=165,
        flag_category="correctness",
        valid_case_ids=["case-a", "case-b"],
    )

    assert updated == _sidecar({"case-a": [_issue(165)]})


def test_record_known_issue_appends_second_entry_and_preserves_existing() -> None:
    updated = known_qa_issues.record_known_issue(
        _sidecar({"case-a": [_issue(165)]}),
        qa_case_id="case-a",
        issue_number=166,
        flag_category="formatting",
        valid_case_ids=["case-a"],
    )

    assert updated == _sidecar({"case-a": [_issue(165), _issue(166, "formatting")]})


def test_record_known_issue_is_idempotent_for_duplicate_mapping() -> None:
    sidecar = _sidecar({"case-a": [_issue(165)]})

    assert (
        known_qa_issues.record_known_issue(
            sidecar,
            qa_case_id="case-a",
            issue_number=165,
            flag_category="correctness",
            valid_case_ids=["case-a"],
        )
        == sidecar
    )


def test_record_known_issue_for_qa_record_adds_entry_for_qa_review_record() -> None:
    updated = known_qa_issues.record_known_issue_for_qa_record(
        _sidecar({}),
        record={
            "source": "qa_review",
            "qa_case_id": "case-a",
            "question": "should not be copied",
            "response_text": "should not be copied",
            "timestamp": "2026-06-03T10:00:00Z",
        },
        issue_number=165,
        flag_category="correctness",
        valid_case_ids=["case-a", "case-b"],
    )

    assert updated == _sidecar({"case-a": [_issue(165)]})
    assert known_qa_issues.serialize_sidecar(updated) == textwrap.dedent(
        """\
        {
          "version": 1,
          "questions": {
            "case-a": [
              {
                "issue_number": 165,
                "flag_category": "correctness"
              }
            ]
          }
        }
        """
    )


def test_record_known_issue_for_qa_record_noops_for_non_qa_source() -> None:
    sidecar = _sidecar({})

    assert (
        known_qa_issues.record_known_issue_for_qa_record(
            sidecar,
            record={
                "source": "slack",
                "qa_case_id": "case-a",
            },
            issue_number=165,
            flag_category="correctness",
            valid_case_ids=["case-a"],
        )
        == sidecar
    )


def test_record_known_issue_for_qa_record_noops_without_non_empty_case_id() -> None:
    sidecar = _sidecar({})

    assert (
        known_qa_issues.record_known_issue_for_qa_record(
            sidecar,
            record={
                "source": "qa_review",
                "qa_case_id": "",
            },
            issue_number=165,
            flag_category="correctness",
            valid_case_ids=["case-a"],
        )
        == sidecar
    )


def test_record_known_issue_for_qa_record_appends_new_flag_for_existing_issue() -> None:
    updated = known_qa_issues.record_known_issue_for_qa_record(
        _sidecar({"case-a": [_issue(165)]}),
        record={
            "source": "qa_review",
            "qa_case_id": "case-a",
        },
        issue_number=165,
        flag_category="formatting",
        valid_case_ids=["case-a"],
    )

    assert updated == _sidecar({"case-a": [_issue(165), _issue(165, "formatting")]})


@pytest.mark.parametrize("qa_case_id", ["case-b", ""])
def test_record_known_issue_rejects_missing_or_unknown_case_ids(
    qa_case_id: str,
) -> None:
    with pytest.raises(ValueError, match="Unknown QA case id in sidecar"):
        known_qa_issues.record_known_issue(
            _sidecar({}),
            qa_case_id=qa_case_id,
            issue_number=165,
            flag_category="correctness",
            valid_case_ids=["case-a"],
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

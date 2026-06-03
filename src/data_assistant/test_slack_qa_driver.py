"""Tests for the Slack QA driver's pure parts.

The driver's ``main`` is near-untested by design (live Slack + live OpenAI,
like the ``live_eval`` mains). This file covers pure parsing, argument,
Known QA Issue preflight, and thread-target resolution behavior with no Slack
and no OpenAI.
"""

from __future__ import annotations

import pathlib
import textwrap

import pytest

import data_assistant.assistant_thread_pointer as assistant_thread_pointer
import data_assistant.known_qa_issues as known_qa_issues
import data_assistant.slack_qa_driver as slack_qa_driver


def test_parse_battery_cases_returns_identified_top_level_cases() -> None:
    markdown = (
        "## Orders\n\n"
        "- [orders-net-revenue-by-store-region-q1-2026] What was total net revenue by "
        "store region in Q1 2026?\n"
        "- [gross-revenue-by-channel-march-2026] What was total gross revenue by "
        "order channel in March 2026?\n"
    )

    assert slack_qa_driver.parse_battery_cases(markdown) == [
        slack_qa_driver.QACase(
            id="orders-net-revenue-by-store-region-q1-2026",
            question="What was total net revenue by store region in Q1 2026?",
        ),
        slack_qa_driver.QACase(
            id="gross-revenue-by-channel-march-2026",
            question="What was total gross revenue by order channel in March 2026?",
        ),
    ]


def test_parse_battery_cases_rejects_unidentified_bullets_by_default() -> None:
    with pytest.raises(ValueError, match="QA case id"):
        slack_qa_driver.parse_battery_cases("- What was total net revenue?\n")


def test_parse_battery_cases_rejects_duplicate_case_ids() -> None:
    markdown = textwrap.dedent(
        """\
        - [duplicate-id] What was total net revenue by store region in Q1 2026?
        - [duplicate-id] What was total gross revenue by order channel in March 2026?
        """
    )

    with pytest.raises(ValueError, match="Duplicate QA case id"):
        slack_qa_driver.parse_battery_cases(markdown)


def test_parse_battery_cases_allows_unidentified_bullets_with_escape_hatch() -> None:
    assert slack_qa_driver.parse_battery_cases(
        "- What was total net revenue?\n",
        allow_unidentified=True,
    ) == [slack_qa_driver.QACase(id=None, question="What was total net revenue?")]


def test_parse_args_accepts_allow_unidentified_cases_flag() -> None:
    args = slack_qa_driver.build_arg_parser().parse_args(["--allow-unidentified-cases"])

    assert args.allow_unidentified_cases is True


def test_parse_args_accepts_known_issue_flags() -> None:
    args = slack_qa_driver.build_arg_parser().parse_args(
        [
            "--known-issues-path",
            "docs/custom.known-issues.json",
            "--skip-known-issue-prune",
        ]
    )

    assert args.known_issues_path == pathlib.Path("docs/custom.known-issues.json")
    assert args.skip_known_issue_prune is True


def test_curated_qa_battery_parses_in_strict_mode() -> None:
    markdown = pathlib.Path(slack_qa_driver.DEFAULT_BATTERY_PATH).read_text(
        encoding="utf-8"
    )

    cases = slack_qa_driver.parse_battery_cases(markdown)

    assert cases
    assert all(case.id for case in cases)


def test_parse_battery_sends_only_top_level_bullets() -> None:
    markdown = textwrap.dedent(
        """\
        # Retail QA Questions

        Use these questions to evaluate the standard Retail dataset.

        ## Revenue

        - What was total revenue by region in January 2026?
        - What was total revenue in the West region for all time?

        ## Customers

        - How many customers were created in January 2026?
        """
    )

    questions = slack_qa_driver.parse_battery(markdown)

    assert questions == [
        "What was total revenue by region in January 2026?",
        "What was total revenue in the West region for all time?",
        "How many customers were created in January 2026?",
    ]


def test_parse_battery_skips_indented_sub_bullets() -> None:
    markdown = textwrap.dedent(
        """\
        ## Known Non-Answer Cases

        - What was total revenue by salesperson in January 2026?
          - expected: Non-Answer (no salesperson dimension)
        - What was customer lifetime value by region?
        \t- expected: Non-Answer (no CLV metric)
        """
    )

    questions = slack_qa_driver.parse_battery(markdown)

    assert questions == [
        "What was total revenue by salesperson in January 2026?",
        "What was customer lifetime value by region?",
    ]


def test_parse_battery_ignores_headings_and_prose() -> None:
    markdown = textwrap.dedent(
        """\
        # Title

        Some prose that mentions a - dash mid sentence.

        ## Section
        Another paragraph.
        """
    )

    assert slack_qa_driver.parse_battery(markdown) == []


def test_parse_battery_strips_surrounding_whitespace() -> None:
    markdown = "-   What was total revenue?   \n"

    assert slack_qa_driver.parse_battery(markdown) == ["What was total revenue?"]


def test_resolve_known_issues_path_honors_override() -> None:
    battery_path = pathlib.Path("docs/qa-retail-questions.md")
    override_path = pathlib.Path("docs/custom-known-issues.json")

    assert (
        slack_qa_driver.resolve_known_issues_path(
            battery_path=battery_path,
            known_issues_path=override_path,
        )
        == override_path
    )


def test_preflight_known_issues_skips_escape_hatch_unidentified_cases(
    tmp_path: pathlib.Path,
) -> None:
    sidecar_path = _sidecar_path(tmp_path)

    slack_qa_driver.preflight_known_issues(
        battery_path=tmp_path / "qa-retail-questions.md",
        cases=[slack_qa_driver.QACase(id=None, question="legacy question")],
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

    with pytest.raises(known_qa_issues.KnownQAIssuePruneError, match="lookup failed"):
        slack_qa_driver.preflight_known_issues(
            battery_path=tmp_path / "qa-retail-questions.md",
            cases=[_case("case-a")],
            known_issues_path=sidecar_path,
            skip_prune=False,
            is_issue_open=fail_lookup,
        )


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

    slack_qa_driver.preflight_known_issues(
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

    slack_qa_driver.preflight_known_issues(
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


@pytest.mark.parametrize(
    (
        "channel",
        "thread_ts",
        "pointer",
        "expected",
    ),
    [
        pytest.param(
            "Cexplicit",
            "1.1",
            ("Cpointer", "9.9"),
            ("Cexplicit", "1.1"),
            id="explicit-args-win",
        ),
        pytest.param(
            None,
            None,
            ("Cpointer", "9.9"),
            ("Cpointer", "9.9"),
            id="fallback-to-pointer",
        ),
        pytest.param(
            "Cexplicit",
            None,
            ("Cpointer", "9.9"),
            ("Cexplicit", "9.9"),
            id="partial-args-fill-from-pointer",
        ),
        pytest.param(
            None,
            None,
            None,
            "No assistant thread found",
            id="missing-args-and-pointer",
        ),
        pytest.param(
            "Cexplicit",
            None,
            None,
            "No assistant thread found",
            id="partial-args-without-pointer",
        ),
    ],
)
def test_resolve_thread_target(
    tmp_path: pathlib.Path,
    channel: str | None,
    thread_ts: str | None,
    pointer: tuple[str, str] | None,
    expected: tuple[str, str] | str,
) -> None:
    pointer_path = tmp_path / "last_assistant_thread.json"
    if pointer is not None:
        assistant_thread_pointer.write_latest(*pointer, path=pointer_path)

    target = slack_qa_driver.resolve_thread_target(
        channel=channel,
        thread_ts=thread_ts,
        pointer_path=pointer_path,
    )

    if isinstance(expected, str):
        assert isinstance(target, str)
        assert expected in target
    else:
        assert target == expected


def _sidecar_path(tmp_path: pathlib.Path) -> pathlib.Path:
    return tmp_path / "qa-retail-questions.known-issues.json"


def _case(case_id: str, *, question: str = "Question?") -> slack_qa_driver.QACase:
    return slack_qa_driver.QACase(id=case_id, question=question)


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

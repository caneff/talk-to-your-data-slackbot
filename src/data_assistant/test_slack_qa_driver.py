"""Tests for the Slack QA driver's pure parts.

The driver's ``main`` is near-untested by design (live Slack + live OpenAI,
like the ``live_eval`` mains). Only the pure battery parser is covered here; it
maps the ``qa-retail-questions.md`` markdown shape to a flat list of
top-level questions with no Slack and no OpenAI.
"""

from __future__ import annotations

import pathlib
import textwrap

import pytest

import data_assistant.assistant_thread_pointer as assistant_thread_pointer
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


def test_resolve_thread_target_uses_explicit_args_over_pointer(
    tmp_path: pathlib.Path,
) -> None:
    pointer_path = tmp_path / "last_assistant_thread.json"
    assistant_thread_pointer.write_latest("Cpointer", "9.9", path=pointer_path)

    target = slack_qa_driver.resolve_thread_target(
        channel="Cexplicit",
        thread_ts="1.1",
        pointer_path=pointer_path,
    )

    # Explicit overrides win even when a pointer exists.
    assert target == ("Cexplicit", "1.1")


def test_resolve_thread_target_falls_back_to_pointer_when_args_missing(
    tmp_path: pathlib.Path,
) -> None:
    pointer_path = tmp_path / "last_assistant_thread.json"
    assistant_thread_pointer.write_latest("Cpointer", "9.9", path=pointer_path)

    target = slack_qa_driver.resolve_thread_target(
        channel=None,
        thread_ts=None,
        pointer_path=pointer_path,
    )

    assert target == ("Cpointer", "9.9")


def test_resolve_thread_target_partial_args_fill_from_pointer(
    tmp_path: pathlib.Path,
) -> None:
    pointer_path = tmp_path / "last_assistant_thread.json"
    assistant_thread_pointer.write_latest("Cpointer", "9.9", path=pointer_path)

    # Only one id passed: the other fills from the pointer.
    target = slack_qa_driver.resolve_thread_target(
        channel="Cexplicit",
        thread_ts=None,
        pointer_path=pointer_path,
    )

    assert target == ("Cexplicit", "9.9")


def test_resolve_thread_target_no_args_no_pointer_returns_error(
    tmp_path: pathlib.Path,
) -> None:
    target = slack_qa_driver.resolve_thread_target(
        channel=None,
        thread_ts=None,
        pointer_path=tmp_path / "missing.json",
    )

    # Unresolved -> a clear operator-facing error message (a str, not a tuple).
    assert isinstance(target, str)
    assert "No assistant thread found" in target


def test_resolve_thread_target_partial_args_no_pointer_returns_error(
    tmp_path: pathlib.Path,
) -> None:
    # One id passed but the other cannot be filled (no pointer) -> still an error.
    target = slack_qa_driver.resolve_thread_target(
        channel="Cexplicit",
        thread_ts=None,
        pointer_path=tmp_path / "missing.json",
    )

    assert isinstance(target, str)
    assert "No assistant thread found" in target

"""Tests for QA battery markdown parsing.

Pure string -> list mapping: no Slack, no OpenAI, no sidecar.
"""

from __future__ import annotations

import pathlib
import textwrap

import pytest

import data_assistant.qa_battery as qa_battery
import data_assistant.slack_qa_driver as slack_qa_driver


def test_parse_battery_cases_returns_identified_top_level_cases() -> None:
    markdown = (
        "## Orders\n\n"
        "- [orders-net-revenue-by-store-region-q1-2026] What was total net revenue by "
        "store region in Q1 2026?\n"
        "- [gross-revenue-by-channel-march-2026] What was total gross revenue by "
        "order channel in March 2026?\n"
    )

    assert qa_battery.parse_battery_cases(markdown) == [
        qa_battery.QACase(
            id="orders-net-revenue-by-store-region-q1-2026",
            question="What was total net revenue by store region in Q1 2026?",
        ),
        qa_battery.QACase(
            id="gross-revenue-by-channel-march-2026",
            question="What was total gross revenue by order channel in March 2026?",
        ),
    ]


def test_parse_battery_cases_rejects_unidentified_bullets_by_default() -> None:
    with pytest.raises(ValueError, match="QA case id"):
        qa_battery.parse_battery_cases("- What was total net revenue?\n")


def test_parse_battery_cases_rejects_duplicate_case_ids() -> None:
    markdown = textwrap.dedent(
        """\
        - [duplicate-id] What was total net revenue by store region in Q1 2026?
        - [duplicate-id] What was total gross revenue by order channel in March 2026?
        """
    )

    with pytest.raises(ValueError, match="Duplicate QA case id"):
        qa_battery.parse_battery_cases(markdown)


def test_parse_battery_cases_allows_unidentified_bullets_with_escape_hatch() -> None:
    assert qa_battery.parse_battery_cases(
        "- What was total net revenue?\n",
        allow_unidentified=True,
    ) == [qa_battery.QACase(id=None, question="What was total net revenue?")]


def test_curated_qa_battery_parses_in_strict_mode() -> None:
    markdown = pathlib.Path(slack_qa_driver.DEFAULT_BATTERY_PATH).read_text(
        encoding="utf-8"
    )

    cases = qa_battery.parse_battery_cases(markdown)

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

    questions = qa_battery.parse_battery(markdown)

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

    questions = qa_battery.parse_battery(markdown)

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

    assert qa_battery.parse_battery(markdown) == []


def test_parse_battery_strips_surrounding_whitespace() -> None:
    markdown = "-   What was total revenue?   \n"

    assert qa_battery.parse_battery(markdown) == ["What was total revenue?"]

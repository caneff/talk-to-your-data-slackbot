"""Shared provider-facing Question Frame cases for evals and demo replay."""

from __future__ import annotations

import dataclasses

import data_assistant.question_interpreter as question_interpreter


@dataclasses.dataclass(frozen=True)
class SharedQuestionFrameCase:
    """One canonical question and expected provider proposal."""

    name: str
    question: str
    expected: question_interpreter.QuestionFrameProposal
    enabled: bool = True


def _proposal(
    *,
    intent: str | None,
    metric: str | None,
    field_operations: tuple[question_interpreter.FieldOperationProposal, ...],
) -> question_interpreter.QuestionFrameProposal:
    return question_interpreter.QuestionFrameProposal(
        intent=intent,
        metric=metric,
        field_operations=field_operations,
    )


def _group_by_region() -> question_interpreter.GroupByOperationProposal:
    return question_interpreter.GroupByOperationProposal(
        operation="group_by",
        field="region",
    )


def _group_by_customer_region() -> question_interpreter.GroupByOperationProposal:
    return question_interpreter.GroupByOperationProposal(
        operation="group_by",
        field="customer region",
    )


def _january_2026_order_date_filter() -> (
    question_interpreter.RangeFilterOperationProposal
):
    return question_interpreter.RangeFilterOperationProposal(
        operation="range_filter",
        field="order date",
        lower="2026-01-01",
        upper="2026-01-31",
    )


def _january_2026_created_date_filter() -> (
    question_interpreter.RangeFilterOperationProposal
):
    return question_interpreter.RangeFilterOperationProposal(
        operation="range_filter",
        field="created date",
        lower="2026-01-01",
        upper="2026-01-31",
    )


def _january_revenue_by_region_proposal() -> question_interpreter.QuestionFrameProposal:
    return _proposal(
        intent="summarize",
        metric="total revenue",
        field_operations=(
            _group_by_region(),
            _january_2026_order_date_filter(),
        ),
    )


def _january_customer_count_by_customer_region_proposal() -> (
    question_interpreter.QuestionFrameProposal
):
    return _proposal(
        intent="summarize",
        metric="customer count",
        field_operations=(
            _group_by_customer_region(),
            _january_2026_created_date_filter(),
        ),
    )


def _missing_time_range_revenue_by_region_proposal() -> (
    question_interpreter.QuestionFrameProposal
):
    return _proposal(
        intent="summarize",
        metric=None,
        field_operations=(_group_by_region(),),
    )


SHARED_QUESTION_FRAME_CASES: tuple[SharedQuestionFrameCase, ...] = (
    SharedQuestionFrameCase(
        name="canonical_question",
        question="What was total revenue by region in January 2026?",
        expected=_january_revenue_by_region_proposal(),
    ),
    SharedQuestionFrameCase(
        name="show_total_revenue_by_region",
        question="Show total revenue by region in January 2026.",
        expected=_january_revenue_by_region_proposal(),
    ),
    SharedQuestionFrameCase(
        name="summarize_total_revenue_by_region",
        question="Summarize total revenue by region for January 2026.",
        expected=_january_revenue_by_region_proposal(),
    ),
    SharedQuestionFrameCase(
        name="customer_count_by_region",
        question="What was customer count by customer region in January 2026?",
        expected=_january_customer_count_by_customer_region_proposal(),
    ),
    SharedQuestionFrameCase(
        name="safe_non_answer_question",
        question="What was total revenue by region?",
        expected=_missing_time_range_revenue_by_region_proposal(),
        enabled=False,
    ),
)

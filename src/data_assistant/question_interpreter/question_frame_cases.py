"""Shared provider-facing Question Frame cases for evals and demo replay.

These cases target the retail Semantic Layer
(`examples/retail_ops_demo/semantic_layer`), the app/QA default that the live
eval loads. Labels here must match the retail YAMLs:
`demo_orders.yaml` (metrics incl. `total net revenue`; fields `store region`,
`order channel`, `order date` range_filter) and `demo_customers.yaml`
(`customer count`; fields `customer region`, `customer created date`).
"""

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
    all_time: bool = False,
    metric_ambiguity: str | None = None,
) -> question_interpreter.QuestionFrameProposal:
    return question_interpreter.QuestionFrameProposal(
        intent=intent,
        metric=metric,
        metric_ambiguity=metric_ambiguity,
        field_operations=field_operations,
        all_time=all_time,
    )


def _group_by_store_region() -> question_interpreter.GroupByOperationProposal:
    return question_interpreter.GroupByOperationProposal(
        operation="group_by",
        field="store region",
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


def _january_2026_customer_created_date_filter() -> (
    question_interpreter.RangeFilterOperationProposal
):
    return question_interpreter.RangeFilterOperationProposal(
        operation="range_filter",
        field="customer created date",
        lower="2026-01-01",
        upper="2026-01-31",
    )


def _order_channel_filter(
    value: str,
) -> question_interpreter.IncludeFilterOperationProposal:
    return question_interpreter.IncludeFilterOperationProposal(
        operation="include_filter",
        field="order channel",
        values=(value,),
    )


def _order_date_filter(
    value: str,
) -> question_interpreter.IncludeFilterOperationProposal:
    return question_interpreter.IncludeFilterOperationProposal(
        operation="include_filter",
        field="order date",
        values=(value,),
    )


def _fulfillment_status_filter(
    value: str,
) -> question_interpreter.IncludeFilterOperationProposal:
    return question_interpreter.IncludeFilterOperationProposal(
        operation="include_filter",
        field="fulfillment status",
        values=(value,),
    )


def _january_net_revenue_by_store_region_proposal() -> (
    question_interpreter.QuestionFrameProposal
):
    return _proposal(
        intent="summarize",
        metric="total net revenue",
        field_operations=(
            _group_by_store_region(),
            _january_2026_order_date_filter(),
        ),
    )


def _january_gross_revenue_by_store_region_proposal() -> (
    question_interpreter.QuestionFrameProposal
):
    return _proposal(
        intent="summarize",
        metric="total gross revenue",
        field_operations=(
            _group_by_store_region(),
            _january_2026_order_date_filter(),
        ),
    )


def _january_net_revenue_rank_store_region_proposal() -> (
    question_interpreter.QuestionFrameProposal
):
    return _proposal(
        intent="rank",
        metric="total net revenue",
        field_operations=(
            _group_by_store_region(),
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
            _january_2026_customer_created_date_filter(),
        ),
    )


def _missing_time_scope_net_revenue_by_store_region_proposal() -> (
    question_interpreter.QuestionFrameProposal
):
    return _proposal(
        intent="summarize",
        metric="total net revenue",
        field_operations=(_group_by_store_region(),),
    )


def _recurring_revenue_metric_ambiguity_proposal() -> (
    question_interpreter.QuestionFrameProposal
):
    return _proposal(
        intent="summarize",
        metric=None,
        metric_ambiguity="total recurring revenue",
        field_operations=(_january_2026_order_date_filter(),),
    )


def _all_time_net_revenue_for_channel_value_proposal(
    value: str,
) -> question_interpreter.QuestionFrameProposal:
    return _proposal(
        intent="summarize",
        metric="total net revenue",
        field_operations=(_order_channel_filter(value),),
        all_time=True,
    )


def _exact_date_net_revenue_proposal() -> question_interpreter.QuestionFrameProposal:
    return _proposal(
        intent="summarize",
        metric="total net revenue",
        field_operations=(_order_date_filter("2026-01-15"),),
    )


def _multi_filter_net_revenue_proposal() -> question_interpreter.QuestionFrameProposal:
    return _proposal(
        intent="summarize",
        metric="total net revenue",
        field_operations=(
            _order_channel_filter("Web"),
            _fulfillment_status_filter("Shipped"),
        ),
        all_time=True,
    )


SHARED_QUESTION_FRAME_CASES: tuple[SharedQuestionFrameCase, ...] = (
    SharedQuestionFrameCase(
        name="canonical_question",
        question="What was total net revenue by store region in January 2026?",
        expected=_january_net_revenue_by_store_region_proposal(),
    ),
    SharedQuestionFrameCase(
        name="show_total_net_revenue_by_store_region",
        question="Show total net revenue by store region in January 2026.",
        expected=_january_net_revenue_by_store_region_proposal(),
    ),
    SharedQuestionFrameCase(
        name="summarize_total_net_revenue_by_store_region",
        question="Summarize total net revenue by store region for January 2026.",
        expected=_january_net_revenue_by_store_region_proposal(),
    ),
    SharedQuestionFrameCase(
        name="rank_total_net_revenue_by_store_region",
        question=(
            "Which store region had the highest total net revenue in January 2026?"
        ),
        expected=_january_net_revenue_rank_store_region_proposal(),
    ),
    SharedQuestionFrameCase(
        name="customer_count_by_customer_region",
        question="What was customer count by customer region in January 2026?",
        expected=_january_customer_count_by_customer_region_proposal(),
    ),
    SharedQuestionFrameCase(
        name="gross_revenue_resolve",
        question="What was total gross revenue by store region in January 2026?",
        expected=_january_gross_revenue_by_store_region_proposal(),
    ),
    SharedQuestionFrameCase(
        name="safe_non_answer_question",
        question="What was total net revenue by store region?",
        expected=_missing_time_scope_net_revenue_by_store_region_proposal(),
    ),
    SharedQuestionFrameCase(
        name="recurring_revenue_metric_ambiguity",
        question="What was total recurring revenue in January 2026?",
        expected=_recurring_revenue_metric_ambiguity_proposal(),
    ),
    SharedQuestionFrameCase(
        name="all_time_net_revenue_for_channel_value",
        question="What was total net revenue for the Web order channel for all time?",
        expected=_all_time_net_revenue_for_channel_value_proposal("Web"),
    ),
    SharedQuestionFrameCase(
        name="exact_date_net_revenue",
        question="What was total net revenue on 2026-01-15?",
        expected=_exact_date_net_revenue_proposal(),
    ),
    SharedQuestionFrameCase(
        name="multi_filter_net_revenue",
        question=(
            "What was total net revenue for the Web order channel and Shipped "
            "fulfillment status for all time?"
        ),
        expected=_multi_filter_net_revenue_proposal(),
    ),
)

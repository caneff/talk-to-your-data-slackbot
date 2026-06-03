"""Shared provider-facing Question Frame cases for evals and demo replay.

These cases target the retail Semantic Layer
(`examples/retail_ops_demo/semantic_layer`), the app/QA default the live eval
loads. Two invariants hold for every case, with the table YAMLs under
`.../semantic_layer/tables/` as the sole authority for both:

- Every metric and field label is copied verbatim from a retail table YAML.
- Each case pairs its metric, groupable field, and date field from the SAME
  table, so the expected proposal is a coherent supported question; cross-table
  combinations are out-of-layer degradation cases handled elsewhere.
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


@dataclasses.dataclass(frozen=True)
class _DateRange:
    """A complete-calendar date range for a range_filter constraint."""

    lower: str
    upper: str


# Complete-calendar bounds for range_filter date constraints.
Q1_2026 = _DateRange("2026-01-01", "2026-03-31")
JANUARY_2026 = _DateRange("2026-01-01", "2026-01-31")
MARCH_2026 = _DateRange("2026-03-01", "2026-03-31")
APRIL_2026 = _DateRange("2026-04-01", "2026-04-30")
MAY_2026 = _DateRange("2026-05-01", "2026-05-31")
JUNE_2026 = _DateRange("2026-06-01", "2026-06-30")
YEAR_2026 = _DateRange("2026-01-01", "2026-12-31")


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


def _summarize(
    metric: str,
    *field_operations: question_interpreter.FieldOperationProposal,
    all_time: bool = False,
) -> question_interpreter.QuestionFrameProposal:
    return _proposal(
        intent="summarize",
        metric=metric,
        field_operations=field_operations,
        all_time=all_time,
    )


def _deferred(
    intent: str,
    metric: str,
    *field_operations: question_interpreter.FieldOperationProposal,
) -> question_interpreter.QuestionFrameProposal:
    return _proposal(
        intent=intent,
        metric=metric,
        field_operations=field_operations,
    )


def _group_by(field: str) -> question_interpreter.GroupByOperationProposal:
    return question_interpreter.GroupByOperationProposal(
        operation="group_by",
        field=field,
    )


def _range_filter(
    field: str,
    *,
    lower: str | None = None,
    upper: str | None = None,
) -> question_interpreter.RangeFilterOperationProposal:
    return question_interpreter.RangeFilterOperationProposal(
        operation="range_filter",
        field=field,
        lower=lower,
        upper=upper,
    )


def _during(
    field: str,
    period: _DateRange,
) -> question_interpreter.RangeFilterOperationProposal:
    return _range_filter(field, lower=period.lower, upper=period.upper)


def _include_filter(
    field: str,
    *values: str,
) -> question_interpreter.IncludeFilterOperationProposal:
    return question_interpreter.IncludeFilterOperationProposal(
        operation="include_filter",
        field=field,
        values=tuple(values),
    )


def _exclude_filter(
    field: str,
    *values: str,
) -> question_interpreter.ExcludeFilterOperationProposal:
    return question_interpreter.ExcludeFilterOperationProposal(
        operation="exclude_filter",
        field=field,
        values=tuple(values),
    )


SHARED_QUESTION_FRAME_CASES: tuple[SharedQuestionFrameCase, ...] = (
    # --- Existing pinned cases (names + questions + expected preserved) ---
    SharedQuestionFrameCase(
        name="canonical_question",
        question="What was total net revenue by store region in January 2026?",
        expected=_summarize(
            "total net revenue",
            _group_by("store region"),
            _during("order date", JANUARY_2026),
        ),
    ),
    SharedQuestionFrameCase(
        name="show_total_net_revenue_by_store_region",
        question="Show total net revenue by store region in January 2026.",
        expected=_summarize(
            "total net revenue",
            _group_by("store region"),
            _during("order date", JANUARY_2026),
        ),
    ),
    SharedQuestionFrameCase(
        name="summarize_total_net_revenue_by_store_region",
        question="Summarize total net revenue by store region for January 2026.",
        expected=_summarize(
            "total net revenue",
            _group_by("store region"),
            _during("order date", JANUARY_2026),
        ),
    ),
    SharedQuestionFrameCase(
        name="rank_total_net_revenue_by_store_region",
        question=(
            "Which store region had the highest total net revenue in January 2026?"
        ),
        expected=_deferred(
            "rank",
            "total net revenue",
            _group_by("store region"),
            _during("order date", JANUARY_2026),
        ),
    ),
    SharedQuestionFrameCase(
        name="customer_count_by_customer_region",
        question="What was customer count by customer region in January 2026?",
        expected=_summarize(
            "customer count",
            _group_by("customer region"),
            _during("customer created date", JANUARY_2026),
        ),
    ),
    SharedQuestionFrameCase(
        name="gross_revenue_resolve",
        question="What was total gross revenue by store region in January 2026?",
        expected=_summarize(
            "total gross revenue",
            _group_by("store region"),
            _during("order date", JANUARY_2026),
        ),
    ),
    SharedQuestionFrameCase(
        name="safe_non_answer_question",
        question="What was total net revenue by store region?",
        expected=_summarize(
            "total net revenue",
            _group_by("store region"),
        ),
    ),
    SharedQuestionFrameCase(
        name="recurring_revenue_metric_ambiguity",
        question="What was total recurring revenue in January 2026?",
        expected=_proposal(
            intent="summarize",
            metric=None,
            metric_ambiguity="total recurring revenue",
            field_operations=(_during("order date", JANUARY_2026),),
        ),
    ),
    SharedQuestionFrameCase(
        name="all_time_net_revenue_for_channel_value",
        question="What was total net revenue for the Web order channel for all time?",
        expected=_summarize(
            "total net revenue",
            _include_filter("order channel", "Web"),
            all_time=True,
        ),
    ),
    SharedQuestionFrameCase(
        name="exact_date_net_revenue",
        question="What was total net revenue on 2026-01-15?",
        expected=_summarize(
            "total net revenue",
            _include_filter("order date", "2026-01-15"),
        ),
    ),
    SharedQuestionFrameCase(
        name="multi_filter_net_revenue",
        question=(
            "What was total net revenue for the Web order channel and Shipped "
            "fulfillment status for all time?"
        ),
        expected=_summarize(
            "total net revenue",
            _include_filter("order channel", "Web"),
            _include_filter("fulfillment status", "Shipped"),
            all_time=True,
        ),
    ),
    # --- New breadth cases: demo_orders metrics/fields ---
    SharedQuestionFrameCase(
        name="discount_amount_by_promotion_code_april",
        question="What was total discount amount by promotion code in April 2026?",
        expected=_summarize(
            "total discount amount",
            _group_by("promotion code"),
            _during("order date", APRIL_2026),
        ),
    ),
    SharedQuestionFrameCase(
        name="order_count_by_fulfillment_status_may",
        question="What was order count by fulfillment status in May 2026?",
        expected=_summarize(
            "order count",
            _group_by("fulfillment status"),
            _during("order date", MAY_2026),
        ),
    ),
    SharedQuestionFrameCase(
        name="order_count_by_shipping_region_april",
        question="What was order count by shipping region in April 2026?",
        expected=_summarize(
            "order count",
            _group_by("shipping region"),
            _during("order date", APRIL_2026),
        ),
    ),
    SharedQuestionFrameCase(
        name="net_revenue_by_customer_segment_all_time",
        question="What was total net revenue by customer segment for all time?",
        expected=_summarize(
            "total net revenue",
            _group_by("customer segment"),
            all_time=True,
        ),
    ),
    SharedQuestionFrameCase(
        name="gross_revenue_by_order_channel_march",
        question="What was total gross revenue by order channel in March 2026?",
        expected=_summarize(
            "total gross revenue",
            _group_by("order channel"),
            _during("order date", MARCH_2026),
        ),
    ),
    # --- New breadth cases: demo_order_lines metrics/fields ---
    SharedQuestionFrameCase(
        name="gross_margin_by_product_category_march",
        question="What was gross margin by product category in March 2026?",
        expected=_summarize(
            "gross margin",
            _group_by("product category"),
            _during("order date", MARCH_2026),
        ),
    ),
    SharedQuestionFrameCase(
        name="line_revenue_by_brand_q1",
        question="What was total line revenue by brand in Q1 2026?",
        expected=_summarize(
            "total line revenue",
            _group_by("brand"),
            _during("order date", Q1_2026),
        ),
    ),
    SharedQuestionFrameCase(
        name="units_sold_by_product_subcategory_april",
        question="What were units sold by product subcategory in April 2026?",
        expected=_summarize(
            "units sold",
            _group_by("product subcategory"),
            _during("order date", APRIL_2026),
        ),
    ),
    SharedQuestionFrameCase(
        name="units_returned_by_product_category_may",
        question="What were units returned by product category in May 2026?",
        expected=_summarize(
            "units returned",
            _group_by("product category"),
            _during("order date", MAY_2026),
        ),
    ),
    SharedQuestionFrameCase(
        name="gross_margin_by_brand_all_time",
        question="What was gross margin by brand for all time?",
        expected=_summarize(
            "gross margin",
            _group_by("brand"),
            all_time=True,
        ),
    ),
    SharedQuestionFrameCase(
        name="line_revenue_excluding_electronics_march",
        question=(
            "What was total line revenue excluding Electronics products in March 2026?"
        ),
        expected=_summarize(
            "total line revenue",
            _exclude_filter("product category", "Electronics"),
            _during("order date", MARCH_2026),
        ),
    ),
    SharedQuestionFrameCase(
        name="line_revenue_for_apparel_march",
        question="What was total line revenue for Apparel products in March 2026?",
        expected=_summarize(
            "total line revenue",
            _include_filter("product category", "Apparel"),
            _during("order date", MARCH_2026),
        ),
    ),
    # --- New breadth cases: demo_customers metrics/fields ---
    SharedQuestionFrameCase(
        name="customer_count_by_customer_segment_all_time",
        question="What was customer count by customer segment for all time?",
        expected=_summarize(
            "customer count",
            _group_by("customer segment"),
            all_time=True,
        ),
    ),
    SharedQuestionFrameCase(
        name="customer_count_by_loyalty_tier_all_time",
        question="What was customer count by loyalty tier for all time?",
        expected=_summarize(
            "customer count",
            _group_by("loyalty tier"),
            all_time=True,
        ),
    ),
    SharedQuestionFrameCase(
        name="customer_count_by_acquisition_channel_2026",
        question=(
            "What was customer count by acquisition channel for customers created "
            "in 2026?"
        ),
        expected=_summarize(
            "customer count",
            _group_by("acquisition channel"),
            _during("customer created date", YEAR_2026),
        ),
    ),
    # --- New breadth cases: demo_products metrics/fields ---
    SharedQuestionFrameCase(
        name="product_count_by_product_category",
        question="What was product count by product category?",
        expected=_summarize(
            "product count",
            _group_by("product category"),
        ),
    ),
    SharedQuestionFrameCase(
        name="product_count_by_brand",
        question="What was product count by brand?",
        expected=_summarize(
            "product count",
            _group_by("brand"),
        ),
    ),
    # --- New breadth cases: demo_stores metrics/fields ---
    SharedQuestionFrameCase(
        name="store_count_by_store_region",
        question="What was store count by store region?",
        expected=_summarize(
            "store count",
            _group_by("store region"),
        ),
    ),
    SharedQuestionFrameCase(
        name="store_count_by_store_channel",
        question="What was store count by store channel?",
        expected=_summarize(
            "store count",
            _group_by("store channel"),
        ),
    ),
    SharedQuestionFrameCase(
        name="stores_opened_before_2024",
        question="How many stores opened before January 2024?",
        expected=_summarize(
            "store count",
            _range_filter("store opened date", upper="2023-12-31"),
        ),
    ),
    SharedQuestionFrameCase(
        name="store_count_excluding_west_region",
        question="What was store count by store region excluding the West region?",
        expected=_summarize(
            "store count",
            _group_by("store region"),
            _exclude_filter("store region", "West"),
        ),
    ),
    # --- New breadth cases: demo_support_tickets metrics/fields ---
    SharedQuestionFrameCase(
        name="ticket_count_by_issue_category_april",
        question="What was support ticket count by issue category in April 2026?",
        expected=_summarize(
            "support ticket count",
            _group_by("issue category"),
            _during("ticket created date", APRIL_2026),
        ),
    ),
    SharedQuestionFrameCase(
        name="ticket_count_by_ticket_priority_may",
        question="What was support ticket count by ticket priority in May 2026?",
        expected=_summarize(
            "support ticket count",
            _group_by("ticket priority"),
            _during("ticket created date", MAY_2026),
        ),
    ),
    SharedQuestionFrameCase(
        name="ticket_count_by_ticket_status_all_time",
        question="What was support ticket count by ticket status for all time?",
        expected=_summarize(
            "support ticket count",
            _group_by("ticket status"),
            all_time=True,
        ),
    ),
    SharedQuestionFrameCase(
        name="ticket_count_excluding_resolved_status",
        question=(
            "What was support ticket count by issue category excluding the "
            "Resolved status?"
        ),
        expected=_summarize(
            "support ticket count",
            _group_by("issue category"),
            _exclude_filter("ticket status", "Resolved"),
        ),
    ),
    SharedQuestionFrameCase(
        name="ticket_count_high_priority_april",
        question=(
            "What was support ticket count for high priority tickets in April 2026?"
        ),
        expected=_summarize(
            "support ticket count",
            _include_filter("ticket priority", "High"),
            _during("ticket created date", APRIL_2026),
        ),
    ),
    # --- New breadth cases: demo_inventory_snapshots metrics/fields ---
    SharedQuestionFrameCase(
        name="stockout_days_by_product_category_may",
        question="What were stockout days by product category in May 2026?",
        expected=_summarize(
            "stockout days",
            _group_by("product category"),
            _during("inventory snapshot date", MAY_2026),
        ),
    ),
    SharedQuestionFrameCase(
        name="on_hand_units_by_product_category_may",
        question="What were on hand units by product category in May 2026?",
        expected=_summarize(
            "on hand units",
            _group_by("product category"),
            _during("inventory snapshot date", MAY_2026),
        ),
    ),
    SharedQuestionFrameCase(
        name="stockout_days_by_product_subcategory_april",
        question="What were stockout days by product subcategory in April 2026?",
        expected=_summarize(
            "stockout days",
            _group_by("product subcategory"),
            _during("inventory snapshot date", APRIL_2026),
        ),
    ),
    SharedQuestionFrameCase(
        name="on_hand_units_by_store_may",
        question="What were on hand units by store in May 2026?",
        expected=_summarize(
            "on hand units",
            _group_by("store"),
            _during("inventory snapshot date", MAY_2026),
        ),
    ),
    SharedQuestionFrameCase(
        name="stockout_days_for_outdoor_products_may",
        question="What were stockout days for Outdoor products in May 2026?",
        expected=_summarize(
            "stockout days",
            _include_filter("inventory product", "Outdoor"),
            _during("inventory snapshot date", MAY_2026),
        ),
    ),
    # --- Deferred intents (Option A: metric + within-table operations set) ---
    SharedQuestionFrameCase(
        name="compare_net_revenue_by_store_region_q1",
        question="How did total net revenue compare by store region in Q1 2026?",
        expected=_deferred(
            "compare",
            "total net revenue",
            _group_by("store region"),
            _during("order date", Q1_2026),
        ),
    ),
    SharedQuestionFrameCase(
        name="trend_order_count_by_order_date_q1",
        question="How did order count trend by order date in Q1 2026?",
        expected=_deferred(
            "trend",
            "order count",
            _group_by("order date"),
            _during("order date", Q1_2026),
        ),
    ),
    SharedQuestionFrameCase(
        name="forecast_stockout_days_june",
        question="Forecast stockout days by product category for June 2026.",
        expected=_deferred(
            "forecast",
            "stockout days",
            _group_by("product category"),
            _during("inventory snapshot date", JUNE_2026),
        ),
    ),
    SharedQuestionFrameCase(
        name="explain_gross_margin_by_brand_q1",
        question="Why did gross margin by brand change in Q1 2026?",
        expected=_deferred(
            "explain",
            "gross margin",
            _group_by("brand"),
            _during("order date", Q1_2026),
        ),
    ),
    SharedQuestionFrameCase(
        name="prescribe_units_returned_by_product_category_may",
        question=(
            "What should we do to reduce units returned by product category in "
            "May 2026?"
        ),
        expected=_deferred(
            "prescribe",
            "units returned",
            _group_by("product category"),
            _during("order date", MAY_2026),
        ),
    ),
    SharedQuestionFrameCase(
        name="diagnose_support_ticket_count_by_issue_category_april",
        question=(
            "Diagnose why support ticket count by issue category spiked in April 2026."
        ),
        expected=_deferred(
            "diagnose",
            "support ticket count",
            _group_by("issue category"),
            _during("ticket created date", APRIL_2026),
        ),
    ),
    # --- Terse conversational variants ---
    SharedQuestionFrameCase(
        name="terse_net_rev_by_store_region_q1",
        question="net rev by store region q1",
        expected=_summarize(
            "total net revenue",
            _group_by("store region"),
            _during("order date", Q1_2026),
        ),
    ),
    SharedQuestionFrameCase(
        name="terse_tickets_by_priority_may",
        question="tickets by priority may",
        expected=_summarize(
            "support ticket count",
            _group_by("ticket priority"),
            _during("ticket created date", MAY_2026),
        ),
    ),
    SharedQuestionFrameCase(
        name="terse_stockout_days_by_category_may",
        question="stockout days by category may",
        expected=_summarize(
            "stockout days",
            _group_by("product category"),
            _during("inventory snapshot date", MAY_2026),
        ),
    ),
    SharedQuestionFrameCase(
        name="terse_margin_by_brand_all_time",
        question="margin by brand all time",
        expected=_summarize(
            "gross margin",
            _group_by("brand"),
            all_time=True,
        ),
    ),
    SharedQuestionFrameCase(
        name="terse_customers_by_loyalty_tier",
        question="customers by loyalty tier",
        expected=_summarize(
            "customer count",
            _group_by("loyalty tier"),
        ),
    ),
    SharedQuestionFrameCase(
        name="terse_stores_by_channel",
        question="stores by channel",
        expected=_summarize(
            "store count",
            _group_by("store channel"),
        ),
    ),
)

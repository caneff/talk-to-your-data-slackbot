"""Shared Provider Proposal cases for evals and demo replay.

These cases target the retail Semantic Layer
(`examples/retail_ops_demo/semantic_layer`), the app/QA default the live eval
loads. Two invariants hold for every case, with the table YAMLs under
`.../semantic_layer/tables/` as the sole authority for both:

- Every metric and field label is copied verbatim from a retail table YAML.
- Each case pairs its metric, groupable field, and date field from the SAME
  table, so the expected proposal is a coherent supported question; cross-table
  combinations are out-of-layer degradation cases handled elsewhere.

The named-but-unavailable-metric cases (#196) are the one deliberate exception
to the first invariant: their `unknown_metric` wording names a metric the retail
layer does NOT carry, so it is intentionally absent from every table YAML. They
sit in their own explicit subgroup, flagged with a comment; the invariant holds
for the `metric`/`field` labels of every other case.
"""

from __future__ import annotations

import dataclasses

import data_assistant.question_interpreter as question_interpreter


@dataclasses.dataclass(frozen=True)
class SharedProviderProposalCase:
    """One canonical question and expected provider proposal."""

    name: str
    question: str
    expected: question_interpreter.ProviderProposal
    enabled: bool = True
    deferred: bool = False


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

# Relative-date windows resolved against as_of_date 2026-06-30 (#197). Each
# covers the most recent COMPLETE unit(s), excluding the in-progress unit that
# contains as_of_date (June / Q2 are excluded; 2026-06-30 itself never lands in
# a window). See ADR-0024.
YESTERDAY = _DateRange("2026-06-29", "2026-06-29")
LAST_7_DAYS = _DateRange("2026-06-23", "2026-06-29")
LAST_30_DAYS = _DateRange("2026-05-31", "2026-06-29")
LAST_TWO_MONTHS = _DateRange("2026-04-01", "2026-05-31")
LAST_THREE_QUARTERS = _DateRange("2025-07-01", "2026-03-31")


def _proposal(
    *,
    intent: str | None,
    metric: str | None,
    field_operations: tuple[question_interpreter.ProviderFieldOperation, ...],
    all_time: bool = False,
    metric_ambiguity: str | None = None,
    unknown_metric: str | None = None,
) -> question_interpreter.ProviderProposal:
    return question_interpreter.ProviderProposal(
        intent=intent,
        metric=metric,
        metric_ambiguity=metric_ambiguity,
        unknown_metric=unknown_metric,
        field_operations=field_operations,
        all_time=all_time,
    )


def _summarize(
    metric: str,
    *field_operations: question_interpreter.ProviderFieldOperation,
    all_time: bool = False,
) -> question_interpreter.ProviderProposal:
    return _proposal(
        intent="summarize",
        metric=metric,
        field_operations=field_operations,
        all_time=all_time,
    )


def _deferred(
    intent: str,
    metric: str,
    *field_operations: question_interpreter.ProviderFieldOperation,
) -> question_interpreter.ProviderProposal:
    return _proposal(
        intent=intent,
        metric=metric,
        field_operations=field_operations,
    )


def _group_by(field: str) -> question_interpreter.ProviderFieldOperation:
    return question_interpreter.ProviderFieldOperation(
        operation="group_by",
        field=field,
    )


def _range_filter(
    field: str,
    *,
    lower: str | None = None,
    upper: str | None = None,
) -> question_interpreter.ProviderFieldOperation:
    return question_interpreter.ProviderFieldOperation(
        operation="range_filter",
        field=field,
        lower=lower,
        upper=upper,
    )


def _during(
    field: str,
    period: _DateRange,
) -> question_interpreter.ProviderFieldOperation:
    return _range_filter(field, lower=period.lower, upper=period.upper)


def _include_filter(
    field: str,
    *values: str,
) -> question_interpreter.ProviderFieldOperation:
    return question_interpreter.ProviderFieldOperation(
        operation="include_filter",
        field=field,
        values=tuple(values),
    )


def _exclude_filter(
    field: str,
    *values: str,
) -> question_interpreter.ProviderFieldOperation:
    return question_interpreter.ProviderFieldOperation(
        operation="exclude_filter",
        field=field,
        values=tuple(values),
    )


SHARED_PROVIDER_PROPOSAL_CASES: tuple[SharedProviderProposalCase, ...] = (
    # --- Existing pinned cases (names + questions + expected preserved) ---
    SharedProviderProposalCase(
        name="canonical_question",
        question="What was total net revenue by store region in January 2026?",
        expected=_summarize(
            "total net revenue",
            _group_by("store region"),
            _during("order date", JANUARY_2026),
        ),
    ),
    SharedProviderProposalCase(
        name="show_total_net_revenue_by_store_region",
        question="Show total net revenue by store region in January 2026.",
        expected=_summarize(
            "total net revenue",
            _group_by("store region"),
            _during("order date", JANUARY_2026),
        ),
    ),
    SharedProviderProposalCase(
        name="summarize_total_net_revenue_by_store_region",
        question="Summarize total net revenue by store region for January 2026.",
        expected=_summarize(
            "total net revenue",
            _group_by("store region"),
            _during("order date", JANUARY_2026),
        ),
    ),
    SharedProviderProposalCase(
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
    SharedProviderProposalCase(
        name="customer_count_by_customer_region",
        question="What was customer count by customer region in January 2026?",
        expected=_summarize(
            "customer count",
            _group_by("customer region"),
            _during("customer created date", JANUARY_2026),
        ),
    ),
    SharedProviderProposalCase(
        name="transactions_alias_resolves_to_order_count",
        question="How many transactions were there in January 2026?",
        expected=_summarize(
            "order count",
            _during("order date", JANUARY_2026),
        ),
    ),
    SharedProviderProposalCase(
        name="gross_revenue_resolve",
        question="What was total gross revenue by store region in January 2026?",
        expected=_summarize(
            "total gross revenue",
            _group_by("store region"),
            _during("order date", JANUARY_2026),
        ),
    ),
    SharedProviderProposalCase(
        name="safe_non_answer_question",
        question="What was total net revenue by store region?",
        expected=_summarize(
            "total net revenue",
            _group_by("store region"),
        ),
    ),
    SharedProviderProposalCase(
        name="recurring_revenue_metric_ambiguity",
        question="What was total recurring revenue in January 2026?",
        expected=_proposal(
            intent="summarize",
            metric=None,
            metric_ambiguity="total recurring revenue",
            field_operations=(_during("order date", JANUARY_2026),),
        ),
    ),
    # --- Named-but-unavailable metric self-report cases (#196) ---
    # These intentionally break the verbatim-label invariant: each unknown_metric
    # names a measure the retail layer does NOT carry (no return-rate, AOV, or
    # conversion-rate metric exists in any table YAML). The interpreter must
    # self-report rather than guess a near label; Provider Proposal Validation
    # routes the report to UNKNOWN_SEMANTIC_LABEL.
    SharedProviderProposalCase(
        name="unknown_metric_return_rate",
        question="What's our return rate?",
        expected=_proposal(
            intent="summarize",
            metric=None,
            unknown_metric="return rate",
            field_operations=(),
        ),
    ),
    SharedProviderProposalCase(
        name="unknown_metric_average_order_value",
        question="What was our average order value in January 2026?",
        expected=_proposal(
            intent="summarize",
            metric=None,
            unknown_metric="average order value",
            field_operations=(_during("order date", JANUARY_2026),),
        ),
    ),
    SharedProviderProposalCase(
        name="unknown_metric_conversion_rate",
        question="What's our conversion rate?",
        expected=_proposal(
            intent="summarize",
            metric=None,
            unknown_metric="conversion rate",
            field_operations=(),
        ),
    ),
    SharedProviderProposalCase(
        name="all_time_net_revenue_for_channel_value",
        question="What was total net revenue for the Web order channel for all time?",
        expected=_summarize(
            "total net revenue",
            _include_filter("order channel", "Web"),
            all_time=True,
        ),
    ),
    SharedProviderProposalCase(
        name="exact_date_net_revenue",
        question="What was total net revenue on 2026-01-15?",
        expected=_summarize(
            "total net revenue",
            _include_filter("order date", "2026-01-15"),
        ),
    ),
    SharedProviderProposalCase(
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
    SharedProviderProposalCase(
        name="discount_amount_by_promotion_code_april",
        question="What was total discount amount by promotion code in April 2026?",
        expected=_summarize(
            "total discount amount",
            _group_by("promotion code"),
            _during("order date", APRIL_2026),
        ),
    ),
    SharedProviderProposalCase(
        name="order_count_by_fulfillment_status_may",
        question="What was order count by fulfillment status in May 2026?",
        expected=_summarize(
            "order count",
            _group_by("fulfillment status"),
            _during("order date", MAY_2026),
        ),
    ),
    SharedProviderProposalCase(
        name="order_count_by_shipping_region_april",
        question="What was order count by shipping region in April 2026?",
        expected=_summarize(
            "order count",
            _group_by("shipping region"),
            _during("order date", APRIL_2026),
        ),
    ),
    SharedProviderProposalCase(
        name="net_revenue_by_customer_segment_all_time",
        question="What was total net revenue by customer segment for all time?",
        expected=_summarize(
            "total net revenue",
            _group_by("customer segment"),
            all_time=True,
        ),
    ),
    SharedProviderProposalCase(
        name="gross_revenue_by_order_channel_march",
        question="What was total gross revenue by order channel in March 2026?",
        expected=_summarize(
            "total gross revenue",
            _group_by("order channel"),
            _during("order date", MARCH_2026),
        ),
    ),
    # --- Degradation cases: shapes validation rejects downstream (#159) ---
    # Multi-group: interpreter faithfully emits both group_by ops; Provider
    # Proposal Validation rejects 2-group shape downstream via
    # UNSUPPORTED_SHAPE (covered by validation unit tests, not here). This
    # case only checks proposal.
    SharedProviderProposalCase(
        name="multi_group_net_revenue_by_region_and_channel",
        question=(
            "What was total net revenue by store region and order channel "
            "in January 2026?"
        ),
        expected=_summarize(
            "total net revenue",
            _group_by("store region"),
            _group_by("order channel"),
            _during("order date", JANUARY_2026),
        ),
    ),
    # Explicit top-N: the model still classifies "top 5 ..." as rank (a deferred
    # intent), unseduced by the explicit count. There is no limit/N field in the
    # schema, so the "5" is intentionally not represented.
    SharedProviderProposalCase(
        name="top_n_store_regions_by_net_revenue",
        question=(
            "What were the top 5 store regions by total net revenue in January 2026?"
        ),
        expected=_deferred(
            "rank",
            "total net revenue",
            _group_by("store region"),
            _during("order date", JANUARY_2026),
        ),
    ),
    # --- New breadth cases: demo_order_lines metrics/fields ---
    SharedProviderProposalCase(
        name="gross_margin_by_product_category_march",
        question="What was gross margin by product category in March 2026?",
        expected=_summarize(
            "gross margin",
            _group_by("product category"),
            _during("order date", MARCH_2026),
        ),
    ),
    SharedProviderProposalCase(
        name="line_revenue_by_brand_q1",
        question="What was total line revenue by brand in Q1 2026?",
        expected=_summarize(
            "total line revenue",
            _group_by("brand"),
            _during("order date", Q1_2026),
        ),
    ),
    SharedProviderProposalCase(
        name="units_sold_by_product_subcategory_april",
        question="What were units sold by product subcategory in April 2026?",
        expected=_summarize(
            "units sold",
            _group_by("product subcategory"),
            _during("order date", APRIL_2026),
        ),
    ),
    SharedProviderProposalCase(
        name="units_returned_by_product_category_may",
        question="What were units returned by product category in May 2026?",
        expected=_summarize(
            "units returned",
            _group_by("product category"),
            _during("order date", MAY_2026),
        ),
    ),
    SharedProviderProposalCase(
        name="gross_margin_by_brand_all_time",
        question="What was gross margin by brand for all time?",
        expected=_summarize(
            "gross margin",
            _group_by("brand"),
            all_time=True,
        ),
    ),
    SharedProviderProposalCase(
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
    SharedProviderProposalCase(
        name="line_revenue_for_apparel_march",
        question="What was total line revenue for Apparel products in March 2026?",
        expected=_summarize(
            "total line revenue",
            _include_filter("product category", "Apparel"),
            _during("order date", MARCH_2026),
        ),
    ),
    # --- New breadth cases: demo_customers metrics/fields ---
    SharedProviderProposalCase(
        name="customer_count_by_customer_segment_all_time",
        question="What was customer count by customer segment for all time?",
        expected=_summarize(
            "customer count",
            _group_by("customer segment"),
            all_time=True,
        ),
    ),
    SharedProviderProposalCase(
        name="customer_count_by_loyalty_tier_all_time",
        question="What was customer count by loyalty tier for all time?",
        expected=_summarize(
            "customer count",
            _group_by("loyalty tier"),
            all_time=True,
        ),
    ),
    SharedProviderProposalCase(
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
    SharedProviderProposalCase(
        name="product_count_by_product_category",
        question="What was product count by product category?",
        expected=_summarize(
            "product count",
            _group_by("product category"),
        ),
    ),
    SharedProviderProposalCase(
        name="product_count_by_brand",
        question="What was product count by brand?",
        expected=_summarize(
            "product count",
            _group_by("brand"),
        ),
    ),
    # --- New breadth cases: demo_stores metrics/fields ---
    SharedProviderProposalCase(
        name="store_count_by_store_region",
        question="What was store count by store region?",
        expected=_summarize(
            "store count",
            _group_by("store region"),
        ),
    ),
    SharedProviderProposalCase(
        name="store_count_by_store_channel",
        question="What was store count by store channel?",
        expected=_summarize(
            "store count",
            _group_by("store channel"),
        ),
    ),
    SharedProviderProposalCase(
        name="stores_opened_before_2024",
        question="How many stores opened before January 2024?",
        expected=_summarize(
            "store count",
            _range_filter("store opened date", upper="2023-12-31"),
        ),
    ),
    SharedProviderProposalCase(
        name="store_count_excluding_west_region",
        question="What was store count by store region excluding the West region?",
        expected=_summarize(
            "store count",
            _group_by("store region"),
            _exclude_filter("store region", "West"),
        ),
    ),
    # --- New breadth cases: demo_support_tickets metrics/fields ---
    SharedProviderProposalCase(
        name="ticket_count_by_issue_category_april",
        question="What was support ticket count by issue category in April 2026?",
        expected=_summarize(
            "support ticket count",
            _group_by("issue category"),
            _during("ticket created date", APRIL_2026),
        ),
    ),
    SharedProviderProposalCase(
        name="ticket_count_by_ticket_priority_may",
        question="What was support ticket count by ticket priority in May 2026?",
        expected=_summarize(
            "support ticket count",
            _group_by("ticket priority"),
            _during("ticket created date", MAY_2026),
        ),
    ),
    SharedProviderProposalCase(
        name="ticket_count_by_ticket_status_all_time",
        question="What was support ticket count by ticket status for all time?",
        expected=_summarize(
            "support ticket count",
            _group_by("ticket status"),
            all_time=True,
        ),
    ),
    SharedProviderProposalCase(
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
    SharedProviderProposalCase(
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
    SharedProviderProposalCase(
        name="stockout_days_by_product_category_may",
        question="What were stockout days by product category in May 2026?",
        expected=_summarize(
            "stockout days",
            _group_by("product category"),
            _during("inventory snapshot date", MAY_2026),
        ),
    ),
    SharedProviderProposalCase(
        name="on_hand_units_by_product_category_may",
        question="What were on hand units by product category in May 2026?",
        expected=_summarize(
            "on hand units",
            _group_by("product category"),
            _during("inventory snapshot date", MAY_2026),
        ),
    ),
    SharedProviderProposalCase(
        name="stockout_days_by_product_subcategory_april",
        question="What were stockout days by product subcategory in April 2026?",
        expected=_summarize(
            "stockout days",
            _group_by("product subcategory"),
            _during("inventory snapshot date", APRIL_2026),
        ),
    ),
    SharedProviderProposalCase(
        name="on_hand_units_by_store_may",
        question="What were on hand units by store in May 2026?",
        expected=_summarize(
            "on hand units",
            _group_by("store"),
            _during("inventory snapshot date", MAY_2026),
        ),
    ),
    SharedProviderProposalCase(
        name="stockout_days_for_outdoor_products_may",
        question="What were stockout days for Outdoor products in May 2026?",
        expected=_summarize(
            "stockout days",
            _include_filter("product category", "Outdoor"),
            _during("inventory snapshot date", MAY_2026),
        ),
    ),
    # --- Deferred intents (Option A: metric + within-table operations set) ---
    SharedProviderProposalCase(
        name="compare_net_revenue_by_store_region_q1",
        question="How did total net revenue compare by store region in Q1 2026?",
        expected=_deferred(
            "compare",
            "total net revenue",
            _group_by("store region"),
            _during("order date", Q1_2026),
        ),
    ),
    SharedProviderProposalCase(
        name="trend_order_count_by_order_date_q1",
        question="How did order count trend by order date in Q1 2026?",
        expected=_deferred(
            "trend",
            "order count",
            _group_by("order date"),
            _during("order date", Q1_2026),
        ),
        deferred=True,
    ),
    SharedProviderProposalCase(
        name="forecast_stockout_days_june",
        question="Forecast stockout days by product category for June 2026.",
        expected=_deferred(
            "forecast",
            "stockout days",
            _group_by("product category"),
            _during("inventory snapshot date", JUNE_2026),
        ),
        deferred=True,
    ),
    SharedProviderProposalCase(
        name="explain_gross_margin_by_brand_q1",
        question="Why did gross margin by brand change in Q1 2026?",
        expected=_deferred(
            "explain",
            "gross margin",
            _group_by("brand"),
            _during("order date", Q1_2026),
        ),
        deferred=True,
    ),
    SharedProviderProposalCase(
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
        deferred=True,
    ),
    SharedProviderProposalCase(
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
    SharedProviderProposalCase(
        name="terse_net_rev_by_store_region_q1",
        question="net rev by store region q1",
        expected=_summarize(
            "total net revenue",
            _group_by("store region"),
            _during("order date", Q1_2026),
        ),
    ),
    SharedProviderProposalCase(
        name="terse_tickets_by_priority_may",
        question="tickets by priority may",
        expected=_summarize(
            "support ticket count",
            _group_by("ticket priority"),
            _during("ticket created date", MAY_2026),
        ),
    ),
    SharedProviderProposalCase(
        name="terse_stockout_days_by_category_may",
        question="stockout days by category may",
        expected=_summarize(
            "stockout days",
            _group_by("product category"),
            _during("inventory snapshot date", MAY_2026),
        ),
    ),
    SharedProviderProposalCase(
        name="terse_margin_by_brand_all_time",
        question="margin by brand all time",
        expected=_summarize(
            "gross margin",
            _group_by("brand"),
            all_time=True,
        ),
    ),
    SharedProviderProposalCase(
        name="terse_customers_by_loyalty_tier",
        question="customers by loyalty tier",
        expected=_summarize(
            "customer count",
            _group_by("loyalty tier"),
        ),
    ),
    SharedProviderProposalCase(
        name="terse_stores_by_channel",
        question="stores by channel",
        expected=_summarize(
            "store count",
            _group_by("store channel"),
        ),
    ),
    # --- Relative date resolution (#197) ---
    # With as_of_date 2026-06-30, a relative window covers the most recent
    # COMPLETE unit(s), excluding the in-progress unit containing as_of_date.
    # June and Q2 are in progress, so "last month" is May and "last quarter" is
    # Q1; 2026-06-29 is the most recent complete day. See ADR-0024.
    #
    # deferred=True on the two quarter cases + last_30_days (#239): the day/month
    # families resolve on the paid live eval, but the model returns the IN-PROGRESS
    # quarter (Q2) for "last quarter"/"last three quarters" (0/3, two prompt
    # attempts), and last_30_days flakes (one sample includes as_of). The
    # convention (ADR-0024) is correct and unchanged; this is a detection gap.
    # Deferred so the eval treats them as known-not-yet and tripwires once a fix
    # makes them pass.
    SharedProviderProposalCase(
        name="relative_yesterday",
        question="What was total net revenue yesterday?",
        expected=_summarize(
            "total net revenue",
            _during("order date", YESTERDAY),
        ),
    ),
    SharedProviderProposalCase(
        name="relative_last_7_days",
        question="What was total net revenue in the last 7 days?",
        expected=_summarize(
            "total net revenue",
            _during("order date", LAST_7_DAYS),
        ),
    ),
    SharedProviderProposalCase(
        name="relative_last_30_days",
        question="What was total net revenue in the last 30 days?",
        expected=_summarize(
            "total net revenue",
            _during("order date", LAST_30_DAYS),
        ),
        deferred=True,
    ),
    SharedProviderProposalCase(
        name="relative_last_month",
        question="What was total net revenue last month?",
        expected=_summarize(
            "total net revenue",
            _during("order date", MAY_2026),
        ),
    ),
    SharedProviderProposalCase(
        name="relative_last_two_months",
        question="What was total net revenue in the last two months?",
        expected=_summarize(
            "total net revenue",
            _during("order date", LAST_TWO_MONTHS),
        ),
    ),
    SharedProviderProposalCase(
        name="relative_last_quarter",
        question="What was total net revenue last quarter?",
        expected=_summarize(
            "total net revenue",
            _during("order date", Q1_2026),
        ),
        deferred=True,
    ),
    SharedProviderProposalCase(
        name="relative_last_three_quarters",
        question="What was total net revenue in the last three quarters?",
        expected=_summarize(
            "total net revenue",
            _during("order date", LAST_THREE_QUARTERS),
        ),
        deferred=True,
    ),
)

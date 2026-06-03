"""Shared provider-facing Question Frame cases for evals and demo replay.

These cases target the retail Semantic Layer
(`examples/retail_ops_demo/semantic_layer`), the app/QA default that the live
eval loads. Every label here is a verbatim retail YAML label, and every case
pairs its metric with a groupable field and date field that live in the SAME
Dataset Table, so each expected proposal is a coherent supported question
(cross-table combinations are out-of-layer degradation cases handled elsewhere).

Table map (label source: `examples/retail_ops_demo/semantic_layer/tables`):

- `demo_orders`: metrics `total net revenue`, `total gross revenue`,
  `order count`, `total discount amount`; groupable `order channel`,
  `fulfillment status`, `promotion code`, `shipping region`, `store region`,
  `customer segment`; date `order date`.
- `demo_order_lines`: metrics `total line revenue`, `gross margin`,
  `units sold`, `units returned`; groupable `product`, `order`,
  `product category`, `product subcategory`, `brand`; date `order date`.
- `demo_customers`: metric `customer count`; groupable `customer segment`,
  `customer region`, `loyalty tier`, `acquisition channel`; date
  `customer created date`.
- `demo_products`: metric `product count`; groupable `product category`,
  `product subcategory`, `brand`; (no date).
- `demo_stores`: metric `store count`; groupable `store region`,
  `store channel`; date `store opened date`.
- `demo_support_tickets`: metric `support ticket count`; groupable
  `issue category`, `ticket priority`, `ticket status`; date
  `ticket created date`.
- `demo_inventory_snapshots`: metrics `on hand units`, `stockout days`;
  groupable `store`, `inventory product`, `product category`,
  `product subcategory`; date `inventory snapshot date`.
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


# Complete-calendar bounds for range_filter date constraints.
_Q1_2026 = ("2026-01-01", "2026-03-31")
_JANUARY_2026 = ("2026-01-01", "2026-01-31")
_MARCH_2026 = ("2026-03-01", "2026-03-31")
_APRIL_2026 = ("2026-04-01", "2026-04-30")
_MAY_2026 = ("2026-05-01", "2026-05-31")
_YEAR_2026 = ("2026-01-01", "2026-12-31")


SHARED_QUESTION_FRAME_CASES: tuple[SharedQuestionFrameCase, ...] = (
    # --- Existing pinned cases (names + questions + expected preserved) ---
    SharedQuestionFrameCase(
        name="canonical_question",
        question="What was total net revenue by store region in January 2026?",
        expected=_proposal(
            intent="summarize",
            metric="total net revenue",
            field_operations=(
                _group_by("store region"),
                _range_filter(
                    "order date", lower=_JANUARY_2026[0], upper=_JANUARY_2026[1]
                ),
            ),
        ),
    ),
    SharedQuestionFrameCase(
        name="show_total_net_revenue_by_store_region",
        question="Show total net revenue by store region in January 2026.",
        expected=_proposal(
            intent="summarize",
            metric="total net revenue",
            field_operations=(
                _group_by("store region"),
                _range_filter(
                    "order date", lower=_JANUARY_2026[0], upper=_JANUARY_2026[1]
                ),
            ),
        ),
    ),
    SharedQuestionFrameCase(
        name="summarize_total_net_revenue_by_store_region",
        question="Summarize total net revenue by store region for January 2026.",
        expected=_proposal(
            intent="summarize",
            metric="total net revenue",
            field_operations=(
                _group_by("store region"),
                _range_filter(
                    "order date", lower=_JANUARY_2026[0], upper=_JANUARY_2026[1]
                ),
            ),
        ),
    ),
    SharedQuestionFrameCase(
        name="rank_total_net_revenue_by_store_region",
        question=(
            "Which store region had the highest total net revenue in January 2026?"
        ),
        expected=_proposal(
            intent="rank",
            metric="total net revenue",
            field_operations=(
                _group_by("store region"),
                _range_filter(
                    "order date", lower=_JANUARY_2026[0], upper=_JANUARY_2026[1]
                ),
            ),
        ),
    ),
    SharedQuestionFrameCase(
        name="customer_count_by_customer_region",
        question="What was customer count by customer region in January 2026?",
        expected=_proposal(
            intent="summarize",
            metric="customer count",
            field_operations=(
                _group_by("customer region"),
                _range_filter(
                    "customer created date",
                    lower=_JANUARY_2026[0],
                    upper=_JANUARY_2026[1],
                ),
            ),
        ),
    ),
    SharedQuestionFrameCase(
        name="gross_revenue_resolve",
        question="What was total gross revenue by store region in January 2026?",
        expected=_proposal(
            intent="summarize",
            metric="total gross revenue",
            field_operations=(
                _group_by("store region"),
                _range_filter(
                    "order date", lower=_JANUARY_2026[0], upper=_JANUARY_2026[1]
                ),
            ),
        ),
    ),
    SharedQuestionFrameCase(
        name="safe_non_answer_question",
        question="What was total net revenue by store region?",
        expected=_proposal(
            intent="summarize",
            metric="total net revenue",
            field_operations=(_group_by("store region"),),
        ),
    ),
    SharedQuestionFrameCase(
        name="recurring_revenue_metric_ambiguity",
        question="What was total recurring revenue in January 2026?",
        expected=_proposal(
            intent="summarize",
            metric=None,
            metric_ambiguity="total recurring revenue",
            field_operations=(
                _range_filter(
                    "order date", lower=_JANUARY_2026[0], upper=_JANUARY_2026[1]
                ),
            ),
        ),
    ),
    SharedQuestionFrameCase(
        name="all_time_net_revenue_for_channel_value",
        question="What was total net revenue for the Web order channel for all time?",
        expected=_proposal(
            intent="summarize",
            metric="total net revenue",
            field_operations=(_include_filter("order channel", "Web"),),
            all_time=True,
        ),
    ),
    SharedQuestionFrameCase(
        name="exact_date_net_revenue",
        question="What was total net revenue on 2026-01-15?",
        expected=_proposal(
            intent="summarize",
            metric="total net revenue",
            field_operations=(_include_filter("order date", "2026-01-15"),),
        ),
    ),
    SharedQuestionFrameCase(
        name="multi_filter_net_revenue",
        question=(
            "What was total net revenue for the Web order channel and Shipped "
            "fulfillment status for all time?"
        ),
        expected=_proposal(
            intent="summarize",
            metric="total net revenue",
            field_operations=(
                _include_filter("order channel", "Web"),
                _include_filter("fulfillment status", "Shipped"),
            ),
            all_time=True,
        ),
    ),
    # --- New breadth cases: demo_orders metrics/fields ---
    SharedQuestionFrameCase(
        name="discount_amount_by_promotion_code_april",
        question="What was total discount amount by promotion code in April 2026?",
        expected=_proposal(
            intent="summarize",
            metric="total discount amount",
            field_operations=(
                _group_by("promotion code"),
                _range_filter("order date", lower=_APRIL_2026[0], upper=_APRIL_2026[1]),
            ),
        ),
    ),
    SharedQuestionFrameCase(
        name="order_count_by_fulfillment_status_may",
        question="What was order count by fulfillment status in May 2026?",
        expected=_proposal(
            intent="summarize",
            metric="order count",
            field_operations=(
                _group_by("fulfillment status"),
                _range_filter("order date", lower=_MAY_2026[0], upper=_MAY_2026[1]),
            ),
        ),
    ),
    SharedQuestionFrameCase(
        name="order_count_by_shipping_region_april",
        question="What was order count by shipping region in April 2026?",
        expected=_proposal(
            intent="summarize",
            metric="order count",
            field_operations=(
                _group_by("shipping region"),
                _range_filter("order date", lower=_APRIL_2026[0], upper=_APRIL_2026[1]),
            ),
        ),
    ),
    SharedQuestionFrameCase(
        name="net_revenue_by_customer_segment_all_time",
        question="What was total net revenue by customer segment for all time?",
        expected=_proposal(
            intent="summarize",
            metric="total net revenue",
            field_operations=(_group_by("customer segment"),),
            all_time=True,
        ),
    ),
    SharedQuestionFrameCase(
        name="gross_revenue_by_order_channel_march",
        question="What was total gross revenue by order channel in March 2026?",
        expected=_proposal(
            intent="summarize",
            metric="total gross revenue",
            field_operations=(
                _group_by("order channel"),
                _range_filter("order date", lower=_MARCH_2026[0], upper=_MARCH_2026[1]),
            ),
        ),
    ),
    # --- New breadth cases: demo_order_lines metrics/fields ---
    SharedQuestionFrameCase(
        name="gross_margin_by_product_category_march",
        question="What was gross margin by product category in March 2026?",
        expected=_proposal(
            intent="summarize",
            metric="gross margin",
            field_operations=(
                _group_by("product category"),
                _range_filter("order date", lower=_MARCH_2026[0], upper=_MARCH_2026[1]),
            ),
        ),
    ),
    SharedQuestionFrameCase(
        name="line_revenue_by_brand_q1",
        question="What was total line revenue by brand in Q1 2026?",
        expected=_proposal(
            intent="summarize",
            metric="total line revenue",
            field_operations=(
                _group_by("brand"),
                _range_filter("order date", lower=_Q1_2026[0], upper=_Q1_2026[1]),
            ),
        ),
    ),
    SharedQuestionFrameCase(
        name="units_sold_by_product_subcategory_april",
        question="What were units sold by product subcategory in April 2026?",
        expected=_proposal(
            intent="summarize",
            metric="units sold",
            field_operations=(
                _group_by("product subcategory"),
                _range_filter("order date", lower=_APRIL_2026[0], upper=_APRIL_2026[1]),
            ),
        ),
    ),
    SharedQuestionFrameCase(
        name="units_returned_by_product_category_may",
        question="What were units returned by product category in May 2026?",
        expected=_proposal(
            intent="summarize",
            metric="units returned",
            field_operations=(
                _group_by("product category"),
                _range_filter("order date", lower=_MAY_2026[0], upper=_MAY_2026[1]),
            ),
        ),
    ),
    SharedQuestionFrameCase(
        name="gross_margin_by_brand_all_time",
        question="What was gross margin by brand for all time?",
        expected=_proposal(
            intent="summarize",
            metric="gross margin",
            field_operations=(_group_by("brand"),),
            all_time=True,
        ),
    ),
    SharedQuestionFrameCase(
        name="line_revenue_excluding_electronics_march",
        question=(
            "What was total line revenue excluding Electronics products in March 2026?"
        ),
        expected=_proposal(
            intent="summarize",
            metric="total line revenue",
            field_operations=(
                _exclude_filter("product category", "Electronics"),
                _range_filter("order date", lower=_MARCH_2026[0], upper=_MARCH_2026[1]),
            ),
        ),
    ),
    SharedQuestionFrameCase(
        name="line_revenue_for_apparel_march",
        question="What was total line revenue for Apparel products in March 2026?",
        expected=_proposal(
            intent="summarize",
            metric="total line revenue",
            field_operations=(
                _include_filter("product category", "Apparel"),
                _range_filter("order date", lower=_MARCH_2026[0], upper=_MARCH_2026[1]),
            ),
        ),
    ),
    # --- New breadth cases: demo_customers metrics/fields ---
    SharedQuestionFrameCase(
        name="customer_count_by_customer_segment_all_time",
        question="What was customer count by customer segment for all time?",
        expected=_proposal(
            intent="summarize",
            metric="customer count",
            field_operations=(_group_by("customer segment"),),
            all_time=True,
        ),
    ),
    SharedQuestionFrameCase(
        name="customer_count_by_loyalty_tier_all_time",
        question="What was customer count by loyalty tier for all time?",
        expected=_proposal(
            intent="summarize",
            metric="customer count",
            field_operations=(_group_by("loyalty tier"),),
            all_time=True,
        ),
    ),
    SharedQuestionFrameCase(
        name="customer_count_by_acquisition_channel_2026",
        question=(
            "What was customer count by acquisition channel for customers created "
            "in 2026?"
        ),
        expected=_proposal(
            intent="summarize",
            metric="customer count",
            field_operations=(
                _group_by("acquisition channel"),
                _range_filter(
                    "customer created date",
                    lower=_YEAR_2026[0],
                    upper=_YEAR_2026[1],
                ),
            ),
        ),
    ),
    # --- New breadth cases: demo_products metrics/fields ---
    SharedQuestionFrameCase(
        name="product_count_by_product_category",
        question="What was product count by product category?",
        expected=_proposal(
            intent="summarize",
            metric="product count",
            field_operations=(_group_by("product category"),),
        ),
    ),
    SharedQuestionFrameCase(
        name="product_count_by_brand",
        question="What was product count by brand?",
        expected=_proposal(
            intent="summarize",
            metric="product count",
            field_operations=(_group_by("brand"),),
        ),
    ),
    # --- New breadth cases: demo_stores metrics/fields ---
    SharedQuestionFrameCase(
        name="store_count_by_store_region",
        question="What was store count by store region?",
        expected=_proposal(
            intent="summarize",
            metric="store count",
            field_operations=(_group_by("store region"),),
        ),
    ),
    SharedQuestionFrameCase(
        name="store_count_by_store_channel",
        question="What was store count by store channel?",
        expected=_proposal(
            intent="summarize",
            metric="store count",
            field_operations=(_group_by("store channel"),),
        ),
    ),
    SharedQuestionFrameCase(
        name="stores_opened_before_2024",
        question="How many stores opened before January 2024?",
        expected=_proposal(
            intent="summarize",
            metric="store count",
            field_operations=(_range_filter("store opened date", upper="2023-12-31"),),
        ),
    ),
    SharedQuestionFrameCase(
        name="store_count_excluding_west_region",
        question="What was store count by store region excluding the West region?",
        expected=_proposal(
            intent="summarize",
            metric="store count",
            field_operations=(
                _group_by("store region"),
                _exclude_filter("store region", "West"),
            ),
        ),
    ),
    # --- New breadth cases: demo_support_tickets metrics/fields ---
    SharedQuestionFrameCase(
        name="ticket_count_by_issue_category_april",
        question="What was support ticket count by issue category in April 2026?",
        expected=_proposal(
            intent="summarize",
            metric="support ticket count",
            field_operations=(
                _group_by("issue category"),
                _range_filter(
                    "ticket created date",
                    lower=_APRIL_2026[0],
                    upper=_APRIL_2026[1],
                ),
            ),
        ),
    ),
    SharedQuestionFrameCase(
        name="ticket_count_by_ticket_priority_may",
        question="What was support ticket count by ticket priority in May 2026?",
        expected=_proposal(
            intent="summarize",
            metric="support ticket count",
            field_operations=(
                _group_by("ticket priority"),
                _range_filter(
                    "ticket created date",
                    lower=_MAY_2026[0],
                    upper=_MAY_2026[1],
                ),
            ),
        ),
    ),
    SharedQuestionFrameCase(
        name="ticket_count_by_ticket_status_all_time",
        question="What was support ticket count by ticket status for all time?",
        expected=_proposal(
            intent="summarize",
            metric="support ticket count",
            field_operations=(_group_by("ticket status"),),
            all_time=True,
        ),
    ),
    SharedQuestionFrameCase(
        name="ticket_count_excluding_resolved_status",
        question=(
            "What was support ticket count by issue category excluding the "
            "Resolved status?"
        ),
        expected=_proposal(
            intent="summarize",
            metric="support ticket count",
            field_operations=(
                _group_by("issue category"),
                _exclude_filter("ticket status", "Resolved"),
            ),
        ),
    ),
    SharedQuestionFrameCase(
        name="ticket_count_high_priority_april",
        question=(
            "What was support ticket count for high priority tickets in April 2026?"
        ),
        expected=_proposal(
            intent="summarize",
            metric="support ticket count",
            field_operations=(
                _include_filter("ticket priority", "High"),
                _range_filter(
                    "ticket created date",
                    lower=_APRIL_2026[0],
                    upper=_APRIL_2026[1],
                ),
            ),
        ),
    ),
    # --- New breadth cases: demo_inventory_snapshots metrics/fields ---
    SharedQuestionFrameCase(
        name="stockout_days_by_product_category_may",
        question="What were stockout days by product category in May 2026?",
        expected=_proposal(
            intent="summarize",
            metric="stockout days",
            field_operations=(
                _group_by("product category"),
                _range_filter(
                    "inventory snapshot date",
                    lower=_MAY_2026[0],
                    upper=_MAY_2026[1],
                ),
            ),
        ),
    ),
    SharedQuestionFrameCase(
        name="on_hand_units_by_product_category_may",
        question="What were on hand units by product category in May 2026?",
        expected=_proposal(
            intent="summarize",
            metric="on hand units",
            field_operations=(
                _group_by("product category"),
                _range_filter(
                    "inventory snapshot date",
                    lower=_MAY_2026[0],
                    upper=_MAY_2026[1],
                ),
            ),
        ),
    ),
    SharedQuestionFrameCase(
        name="stockout_days_by_product_subcategory_april",
        question="What were stockout days by product subcategory in April 2026?",
        expected=_proposal(
            intent="summarize",
            metric="stockout days",
            field_operations=(
                _group_by("product subcategory"),
                _range_filter(
                    "inventory snapshot date",
                    lower=_APRIL_2026[0],
                    upper=_APRIL_2026[1],
                ),
            ),
        ),
    ),
    SharedQuestionFrameCase(
        name="on_hand_units_by_store_may",
        question="What were on hand units by store in May 2026?",
        expected=_proposal(
            intent="summarize",
            metric="on hand units",
            field_operations=(
                _group_by("store"),
                _range_filter(
                    "inventory snapshot date",
                    lower=_MAY_2026[0],
                    upper=_MAY_2026[1],
                ),
            ),
        ),
    ),
    SharedQuestionFrameCase(
        name="stockout_days_for_outdoor_products_may",
        question="What were stockout days for Outdoor products in May 2026?",
        expected=_proposal(
            intent="summarize",
            metric="stockout days",
            field_operations=(
                _include_filter("inventory product", "Outdoor"),
                _range_filter(
                    "inventory snapshot date",
                    lower=_MAY_2026[0],
                    upper=_MAY_2026[1],
                ),
            ),
        ),
    ),
    # --- Deferred intents (Option A: metric + within-table operations set) ---
    SharedQuestionFrameCase(
        name="compare_net_revenue_by_store_region_q1",
        question="How did total net revenue compare by store region in Q1 2026?",
        expected=_proposal(
            intent="compare",
            metric="total net revenue",
            field_operations=(
                _group_by("store region"),
                _range_filter("order date", lower=_Q1_2026[0], upper=_Q1_2026[1]),
            ),
        ),
    ),
    SharedQuestionFrameCase(
        name="trend_order_count_by_order_date_q1",
        question="How did order count trend by order date in Q1 2026?",
        expected=_proposal(
            intent="trend",
            metric="order count",
            field_operations=(
                _group_by("order date"),
                _range_filter("order date", lower=_Q1_2026[0], upper=_Q1_2026[1]),
            ),
        ),
    ),
    SharedQuestionFrameCase(
        name="forecast_stockout_days_june",
        question="Forecast stockout days by product category for June 2026.",
        expected=_proposal(
            intent="forecast",
            metric="stockout days",
            field_operations=(
                _group_by("product category"),
                _range_filter(
                    "inventory snapshot date",
                    lower="2026-06-01",
                    upper="2026-06-30",
                ),
            ),
        ),
    ),
    SharedQuestionFrameCase(
        name="explain_gross_margin_by_brand_q1",
        question="Why did gross margin by brand change in Q1 2026?",
        expected=_proposal(
            intent="explain",
            metric="gross margin",
            field_operations=(
                _group_by("brand"),
                _range_filter("order date", lower=_Q1_2026[0], upper=_Q1_2026[1]),
            ),
        ),
    ),
    SharedQuestionFrameCase(
        name="prescribe_units_returned_by_product_category_may",
        question=(
            "What should we do to reduce units returned by product category in "
            "May 2026?"
        ),
        expected=_proposal(
            intent="prescribe",
            metric="units returned",
            field_operations=(
                _group_by("product category"),
                _range_filter("order date", lower=_MAY_2026[0], upper=_MAY_2026[1]),
            ),
        ),
    ),
    SharedQuestionFrameCase(
        name="diagnose_support_ticket_count_by_issue_category_april",
        question=(
            "Diagnose why support ticket count by issue category spiked in April 2026."
        ),
        expected=_proposal(
            intent="diagnose",
            metric="support ticket count",
            field_operations=(
                _group_by("issue category"),
                _range_filter(
                    "ticket created date",
                    lower=_APRIL_2026[0],
                    upper=_APRIL_2026[1],
                ),
            ),
        ),
    ),
    # --- Terse conversational variants ---
    SharedQuestionFrameCase(
        name="terse_net_rev_by_store_region_q1",
        question="net rev by store region q1",
        expected=_proposal(
            intent="summarize",
            metric="total net revenue",
            field_operations=(
                _group_by("store region"),
                _range_filter("order date", lower=_Q1_2026[0], upper=_Q1_2026[1]),
            ),
        ),
    ),
    SharedQuestionFrameCase(
        name="terse_tickets_by_priority_may",
        question="tickets by priority may",
        expected=_proposal(
            intent="summarize",
            metric="support ticket count",
            field_operations=(
                _group_by("ticket priority"),
                _range_filter(
                    "ticket created date",
                    lower=_MAY_2026[0],
                    upper=_MAY_2026[1],
                ),
            ),
        ),
    ),
    SharedQuestionFrameCase(
        name="terse_stockout_days_by_category_may",
        question="stockout days by category may",
        expected=_proposal(
            intent="summarize",
            metric="stockout days",
            field_operations=(
                _group_by("product category"),
                _range_filter(
                    "inventory snapshot date",
                    lower=_MAY_2026[0],
                    upper=_MAY_2026[1],
                ),
            ),
        ),
    ),
    SharedQuestionFrameCase(
        name="terse_margin_by_brand_all_time",
        question="margin by brand all time",
        expected=_proposal(
            intent="summarize",
            metric="gross margin",
            field_operations=(_group_by("brand"),),
            all_time=True,
        ),
    ),
    SharedQuestionFrameCase(
        name="terse_customers_by_loyalty_tier",
        question="customers by loyalty tier",
        expected=_proposal(
            intent="summarize",
            metric="customer count",
            field_operations=(_group_by("loyalty tier"),),
        ),
    ),
    SharedQuestionFrameCase(
        name="terse_stores_by_channel",
        question="stores by channel",
        expected=_proposal(
            intent="summarize",
            metric="store count",
            field_operations=(_group_by("store channel"),),
        ),
    ),
)

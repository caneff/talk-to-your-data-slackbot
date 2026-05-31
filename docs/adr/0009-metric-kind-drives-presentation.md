# Metric Kind Drives Value Presentation

## Status

Accepted

## Context

Metric values are formatted as money in two places: `reasoning_layer.draft_answer`
formats the aggregate value with `_format_money`, and
`response_composer.compose_final_response` maps `_format_money` over every
dimension row (in a variable literally named `revenue_lines`). The
`schema.Metric` model carries `metric_id`, `label`, `expression`, and
`source_column` — nothing that says what *kind* of quantity the metric is.

This is correct only because `total_revenue` is the single metric with a data
spine. The moment a second metric becomes answerable — `customer_count`, already
defined in `customers.yaml` — the hardcoding renders a count of customers as
`$1,234.00`. The Semantic Layer is expected to grow to many tables and metrics,
so presentation needs to scale by adding configuration, not by adding branches
in the rendering layers.

A `Metric` cannot reliably derive its kind from existing fields:
`total_revenue` is `sum(revenue)` over a `decimal` column, but `customer_count`
is `count(customer_id)` over a `string` identifier. Money-vs-count is not
recoverable from the column data type.

## Decision

A `Metric` declares its presentation kind as a closed enum (`money`, `count`,
and further kinds as needed, such as `ratio`). A single formatter, keyed by
metric kind, owns value rendering and is used by both the Reasoning Layer and
the Response Composer. The duplicated `_format_money` helpers and the
`revenue_lines` naming are removed in favor of that shared, kind-aware
formatter.

Metric Kind is distinct from the Semantic Field `DataType` used to validate and
coerce filter values (ADR-0008): `DataType` governs trusted input typing,
Metric Kind governs output presentation. They are not the same axis and are not
merged.

## Consequences

Adding a metric of a new shape is a YAML change plus, at most, one new entry in
the formatter registry — not an edit threaded through two rendering modules. The
formatter set stays a small, reviewable, closed list, which suits a
trust-focused product where how money renders should not be decided by arbitrary
config. Existing metrics are classified explicitly: `total_revenue` is `money`,
`customer_count` is `count`.

## Alternatives considered

- **Infer kind from `data_type` / `semantic_role`.** Rejected: `count(...)` over
  a `string` identifier and `sum(...)` over a `decimal` column cannot be told
  apart by type, so inference would misclassify the first real second metric.
- **A freeform format string on `Metric`** (e.g. `"$,.2f"`). Rejected: it pushes
  presentation rules into config, invites inconsistent renderings of the same
  kind, and lets arbitrary formatting decisions for sensitive values like money
  live outside reviewed code.

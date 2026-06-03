# Retail QA Questions

Use these questions to evaluate the Retail Operations dataset (the app-run
default layer, `examples/retail_ops_demo/semantic_layer`). The dataset covers
orders, order lines, customers, products, stores, support tickets, and inventory
snapshots, with data refreshed through 2026-05-31.

Top-level `- ` bullets are the questions the QA driver sends. Headings, prose,
and indented sub-bullets are maintainer reference only — they are never sent and
never auto-checked. The human is the only oracle; there is no expected-answer
comparison.

## Orders And Revenue

- What was total net revenue by store region in Q1 2026?
- What was total gross revenue by order channel in March 2026?
- What was total discount amount by promotion code in April 2026?
- What was order count by fulfillment status in May 2026?
- What was total net revenue by customer segment for all time?
- What was total net revenue for Web orders in Q1 2026?
- What was order count by shipping region in April 2026?
- What was total net revenue by order date in March 2026?

## Product Sales And Margin

- What was gross margin by product category in March 2026?
- What was total line revenue by brand in Q1 2026?
- What were units sold by product subcategory in April 2026?
- What were units returned by product category in May 2026?
- What was gross margin by brand for all time?
- What was total line revenue excluding Electronics products in March 2026?
- What was total line revenue for Apparel products in March 2026?
- What were units sold by product category excluding Electronics?

## Customers

- What was customer count by customer segment for all time?
- What was customer count by loyalty tier for all time?
- What was customer count by acquisition channel for all time?
- What was customer count by customer region for all time?
- How many customers were created in January 2026?
- What was customer count by acquisition channel for customers created in 2026?

## Stores And Products

- What was store count by store region?
- What was store count by store channel?
- What was product count by product category?
- What was product count by brand?
- How many stores opened before January 2024?
- What was store count by store region excluding the West region?

## Support Operations

- What was support ticket count by issue category in April 2026?
- What was support ticket count by ticket priority in May 2026?
- What was support ticket count by ticket status for all time?
- What was support ticket count by issue category excluding the Resolved status?
- What was support ticket count for high priority tickets in April 2026?

## Inventory Health

- What were stockout days by product category in May 2026?
- What were on hand units by product category in May 2026?
- What were stockout days by product subcategory in April 2026?
- What were on hand units by store in May 2026?
- What were stockout days for Outdoor products in May 2026?

## Known Non-Answer Cases

These should return Non-Answers rather than guessed results.

- What was total net revenue?
  - Expected reason: missing time scope.
- What was gross margin?
  - Expected reason: missing time scope.
- What was support ticket count?
  - Expected reason: missing time scope.
- What was support ticket count excluding resolved tickets?
  - Expected reason: missing time scope.
- What was total net revenue by product category in March 2026?
  - Expected reason: no single Dataset Table has both `total net revenue`
    (demo_orders) and `product category` (demo_order_lines / demo_products /
    demo_inventory_snapshots).
- What was gross margin by store region in Q1 2026?
  - Expected reason: no single Dataset Table has both `gross margin`
    (demo_order_lines) and `store region` (demo_orders / demo_stores).
- What was support ticket count by loyalty tier in April 2026?
  - Expected reason: no single Dataset Table has both `support ticket count`
    (demo_support_tickets) and `loyalty tier` (demo_customers).
- What were stockout days by store region in May 2026?
  - Expected reason: no single Dataset Table has both `stockout days`
    (demo_inventory_snapshots) and `store region` (demo_orders / demo_stores).
- What was average resolution time by issue category in April 2026?
  - Expected reason: `average resolution time` is not a defined metric (the only
    support metric is `support ticket count`).
- What was return rate by product category in May 2026?
  - Expected reason: `return rate` is not a defined metric.
- What was total net revenue by store region and customer segment in Q1 2026?
  - Expected reason: multi-grouping shape (two dimensions) is unsupported.
- Which store region had the highest total net revenue in Q1 2026?
  - Expected reason: rank / top-N is an unsupported intent.
- Which product category had the most stockout days in May 2026?
  - Expected reason: rank / top-N is an unsupported intent.
- Which issue category had the highest support ticket count?
  - Expected reason: rank / top-N is an unsupported intent.
- Which order channel had the highest total gross revenue in March 2026?
  - Expected reason: rank / top-N is an unsupported intent.
- Which product category had the highest units returned in May 2026?
  - Expected reason: rank / top-N is an unsupported intent.
- Which loyalty tier had the highest customer count?
  - Expected reason: rank / top-N is an unsupported intent.
- Which inventory product had the highest on hand units?
  - Expected reason: rank / top-N is an unsupported intent.
- How did total net revenue compare by store region in Q1 2026?
  - Expected reason: compare is an unsupported intent.
- Forecast stockout days for June 2026.
  - Expected reason: forecasting is an unsupported intent.
- What were stockout days by product category in July 2026?
  - Expected reason: time scope is outside the data window (data runs through
    2026-05-31).
- What was total net revenue yesterday?
  - Expected reason: relative-date phrasing is unsupported (queries need an
    absolute time scope).
- Upload this CSV and show support tickets by priority.
  - Expected reason: user-provided CSV files are not supported data sources.

## Conversational Variants

Use these to test terse, casual, or incomplete phrasing users might type in
Slack.

- net rev by store region q1
- gross revenue by channel in march
- discount by promo code april
- orders by fulfillment status may
- net revenue by customer segment all time
- web revenue q1
- orders by shipping region april
- net revenue by day in march
- margin by category march
- line revenue by brand q1
- units sold by subcategory april
- units returned by category may
- margin by brand all time
- line revenue except electronics march
- customers by segment
- customers by loyalty tier
- customers by acquisition channel
- customers by region
- how many customers joined in jan
- stores by region
- stores by channel
- products by category
- products by brand
- tickets by issue in april
- tickets by priority may
- tickets by status all time
- tickets by issue excluding resolved
- stockout days by category may
- on hand units by category may
- stockout days by subcategory april
- on hand units by store may
- best channel by gross revenue
- apparel sales march
- most returned category
- units sold except electronics
- new customers by acquisition channel this year
- top loyalty tier by customer count
- stores opened before 2024
- stores not in west
- open vs resolved tickets
- high priority tickets april
- biggest support issue
- tickets excluding resolved
- outdoor stockouts may
- which product has most inventory
- yesterday net revenue

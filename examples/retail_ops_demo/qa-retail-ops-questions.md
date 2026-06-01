# Retail Operations QA Questions

Use these questions to evaluate the expanded Retail Operations demo dataset. The
dataset covers orders, order lines, customers, products, stores, support tickets,
and inventory snapshots, with data refreshed through 2026-05-31.

## Orders And Revenue

- What was total net revenue by store region in Q1 2026?
- What was total gross revenue by order channel in March 2026?
- What was total discount amount by promotion code in April 2026?
- What was order count by fulfillment status in May 2026?
- What was total net revenue by customer segment for all time?
- What was total net revenue for Web orders in Q1 2026?
- What was order count by shipping region in April 2026?
- Which order channel had the highest total gross revenue in March 2026?

## Product Sales And Margin

- What was gross margin by product category in March 2026?
- What was total line revenue by brand in Q1 2026?
- What were units sold by product subcategory in April 2026?
- What were units returned by product category in May 2026?
- What was gross margin by brand for all time?
- What was total line revenue for Apparel products in March 2026?
- Which product category had the highest units returned in May 2026?
- What were units sold by product category excluding Electronics?

## Customers

- What was customer count by customer segment for all time?
- What was customer count by loyalty tier for all time?
- What was customer count by acquisition channel for customers created in 2026?
- What was customer count by customer region for all time?
- How many customers were created in January 2026?
- Which loyalty tier had the highest customer count?

## Stores

- What was store count by store region?
- What was store count by store channel?
- How many stores opened before January 2024?
- What was store count by store region excluding the West region?

## Support Operations

- What was support ticket count by issue category in April 2026?
- What was support ticket count by ticket priority in May 2026?
- What was support ticket count by ticket status for all time?
- What was support ticket count for high priority tickets in April 2026?
- Which issue category had the highest support ticket count?
- What was support ticket count excluding resolved tickets?

## Inventory Health

- Which product categories had the most stockout days in May 2026?
- What were on hand units by product category in May 2026?
- What were stockout days by product subcategory in April 2026?
- What were on hand units by store in May 2026?
- What were stockout days for Outdoor products in May 2026?
- Which inventory product had the highest on hand units?

## Edge Cases

- What was total net revenue by product category in March 2026?
- What was gross margin by store region in Q1 2026?
- What was support ticket count by loyalty tier in April 2026?
- What were stockout days by store region in May 2026?
- What was average resolution time by issue category in April 2026?
- What was total net revenue yesterday?

## Known Non-Answer Cases

These should return Non-Answers rather than guessed results.

- What was total net revenue?
  - Expected reason: missing time scope.
- What was gross margin?
  - Expected reason: missing time scope.
- What was total net revenue by product category in March 2026?
  - Expected reason: no single Dataset Table has both `total net revenue` and
    `product category`.
- What was gross margin by store region in Q1 2026?
  - Expected reason: no single Dataset Table has both `gross margin` and
    `store region`.
- What was support ticket count by loyalty tier in April 2026?
  - Expected reason: no single Dataset Table has both `support ticket count`
    and `loyalty tier`.
- What were stockout days by store region in May 2026?
  - Expected reason: no single Dataset Table has both `stockout days` and
    `store region`.
- What was average resolution time by issue category in April 2026?
  - Expected reason: `average resolution time` is not a defined metric.
- What was return rate by product category in May 2026?
  - Expected reason: `return rate` is not a defined metric.
- What was total net revenue by store region and product category in March 2026?
  - Expected reason: multi-table or multi-grouping shape is unsupported.
- Upload this CSV and show support tickets by priority.
  - Expected reason: user-provided CSV files are not supported data sources.
- Forecast stockout days for June 2026.
  - Expected reason: forecasting is an unsupported intent.

## Conversational Variants

Use these to test terse, casual, or incomplete phrasing users might type in
Slack.

- net rev by store region q1
- gross revenue by channel in march
- discount by promo code april
- orders by fulfillment status may
- revenue by customer segment
- web revenue q1
- orders by shipping region
- best channel by gross revenue
- margin by category march
- line revenue by brand
- units sold by subcategory april
- returns by category in may
- margin by brand all time
- apparel sales march
- most returned category
- units sold except electronics
- customers by segment
- customers by loyalty tier
- new customers by acquisition channel this year
- customers by region
- how many customers joined in jan
- top loyalty tier by customer count
- stores by region
- stores by channel
- stores opened before 2024
- stores not in west
- tickets by issue in april
- tickets by priority may
- open vs resolved tickets
- high priority tickets april
- biggest support issue
- tickets excluding resolved
- stockouts by category may
- on hand inventory by category
- stockout days by subcategory
- inventory by store
- outdoor stockouts may
- which product has most inventory
- net revenue by product category
- margin by store region
- tickets by loyalty tier
- stockouts by store region
- avg resolution time by issue
- yesterday net revenue

# Retail QA Questions

Use these questions to evaluate the Retail Operations dataset (the app-run
default layer, `examples/retail_ops_demo/semantic_layer`). The dataset covers
orders, order lines, customers, products, stores, support tickets, and inventory
snapshots, with data refreshed through 2026-05-31.

Top-level `- ` bullets are the questions the QA driver sends. Curated battery
entries must use `- [qa-case-id] Question text` so each case has a stable
durable id. Headings, prose, and indented sub-bullets are maintainer reference
only — they are never sent and never auto-checked. The human is the only
oracle; there is no expected-answer comparison.

## Orders And Revenue

- [orders-net-revenue-by-store-region-q1-2026] What was total net revenue by store region in Q1 2026?
- [orders-gross-revenue-by-order-channel-march-2026] What was total gross revenue by order channel in March 2026?
- [orders-discount-amount-by-promotion-code-april-2026] What was total discount amount by promotion code in April 2026?
- [orders-order-count-by-fulfillment-status-may-2026] What was order count by fulfillment status in May 2026?
- [orders-net-revenue-by-customer-segment-all-time] What was total net revenue by customer segment for all time?
- [orders-net-revenue-web-orders-q1-2026] What was total net revenue for Web orders in Q1 2026?
- [orders-order-count-by-shipping-region-april-2026] What was order count by shipping region in April 2026?
- [orders-net-revenue-by-order-date-march-2026] What was total net revenue by order date in March 2026?
- [orders-top-5-store-regions-by-net-revenue-q1-2026] What were the top 5 store regions by total net revenue in Q1 2026?

## Product Sales And Margin

- [products-gross-margin-by-category-march-2026] What was gross margin by product category in March 2026?
- [products-line-revenue-by-brand-q1-2026] What was total line revenue by brand in Q1 2026?
- [products-units-sold-by-subcategory-april-2026] What were units sold by product subcategory in April 2026?
- [products-units-returned-by-category-may-2026] What were units returned by product category in May 2026?
- [products-gross-margin-by-brand-all-time] What was gross margin by brand for all time?
- [products-line-revenue-excluding-electronics-march-2026] What was total line revenue excluding Electronics products in March 2026?
- [products-line-revenue-apparel-march-2026] What was total line revenue for Apparel products in March 2026?
- [products-units-sold-by-category-excluding-electronics] What were units sold by product category excluding Electronics?
- [products-bottom-3-categories-by-gross-margin-march-2026] What were the bottom 3 product categories by gross margin in March 2026?

## Customers

- [customers-count-by-segment-all-time] What was customer count by customer segment for all time?
- [customers-count-by-loyalty-tier-all-time] What was customer count by loyalty tier for all time?
- [customers-count-by-acquisition-channel-all-time] What was customer count by acquisition channel for all time?
- [customers-count-by-region-all-time] What was customer count by customer region for all time?
- [customers-created-january-2026] How many customers were created in January 2026?
- [customers-count-by-acquisition-channel-created-2026] What was customer count by acquisition channel for customers created in 2026?

## Stores And Products

- [stores-count-by-region] What was store count by store region?
- [stores-count-by-channel] What was store count by store channel?
- [products-count-by-category] What was product count by product category?
- [products-count-by-brand] What was product count by brand?
- [stores-opened-before-january-2024] How many stores opened before January 2024?
- [stores-count-by-region-excluding-west] What was store count by store region excluding the West region?

## Support Operations

- [support-ticket-count-by-issue-category-april-2026] What was support ticket count by issue category in April 2026?
- [support-ticket-count-by-priority-may-2026] What was support ticket count by ticket priority in May 2026?
- [support-ticket-count-by-status-all-time] What was support ticket count by ticket status for all time?
- [support-ticket-count-by-issue-category-excluding-resolved] What was support ticket count by issue category excluding the Resolved status?
- [support-ticket-count-high-priority-april-2026] What was support ticket count for high priority tickets in April 2026?

## Inventory Health

- [inventory-stockout-days-by-category-may-2026] What were stockout days by product category in May 2026?
- [inventory-on-hand-units-by-category-may-2026] What were on hand units by product category in May 2026?
- [inventory-stockout-days-by-subcategory-april-2026] What were stockout days by product subcategory in April 2026?
- [inventory-on-hand-units-by-store-may-2026] What were on hand units by store in May 2026?
- [inventory-stockout-days-outdoor-products-may-2026] What were stockout days for Outdoor products in May 2026?

## Known Non-Answer Cases

These should return Non-Answers rather than guessed results.

- [non-answer-total-net-revenue-no-time-scope] What was total net revenue?
  - Expected reason: missing time scope.
- [non-answer-gross-margin-no-time-scope] What was gross margin?
  - Expected reason: missing time scope.
- [non-answer-support-ticket-count-no-time-scope] What was support ticket count?
  - Expected reason: missing time scope.
- [non-answer-support-ticket-count-excluding-resolved-no-time-scope] What was support ticket count excluding resolved tickets?
  - Expected reason: missing time scope.
- [non-answer-net-revenue-by-product-category-march-2026] What was total net revenue by product category in March 2026?
  - Expected reason: no single Dataset Table has both `total net revenue`
    (demo_orders) and `product category` (demo_order_lines / demo_products /
    demo_inventory_snapshots).
- [non-answer-gross-margin-by-store-region-q1-2026] What was gross margin by store region in Q1 2026?
  - Expected reason: no single Dataset Table has both `gross margin`
    (demo_order_lines) and `store region` (demo_orders / demo_stores).
- [non-answer-support-ticket-count-by-loyalty-tier-april-2026] What was support ticket count by loyalty tier in April 2026?
  - Expected reason: no single Dataset Table has both `support ticket count`
    (demo_support_tickets) and `loyalty tier` (demo_customers).
- [non-answer-stockout-days-by-store-region-may-2026] What were stockout days by store region in May 2026?
  - Expected reason: no single Dataset Table has both `stockout days`
    (demo_inventory_snapshots) and `store region` (demo_orders / demo_stores).
- [non-answer-average-resolution-time-by-issue-category-april-2026] What was average resolution time by issue category in April 2026?
  - Expected reason: `average resolution time` is not a defined metric (the only
    support metric is `support ticket count`).
- [non-answer-return-rate-by-product-category-may-2026] What was return rate by product category in May 2026?
  - Expected reason: `return rate` is not a defined metric.
- [non-answer-net-revenue-by-store-region-and-customer-segment-q1-2026] What was total net revenue by store region and customer segment in Q1 2026?
  - Expected reason: multi-grouping shape (two dimensions) is unsupported.
- [non-answer-top-issue-category-support-ticket-count] Which issue category had the highest support ticket count?
  - Expected reason: missing time scope.
- [non-answer-top-loyalty-tier-customer-count] Which loyalty tier had the highest customer count?
  - Expected reason: missing time scope.
- [non-answer-top-inventory-product-on-hand-units] Which inventory product had the highest on hand units?
  - Expected reason: missing time scope.
- [non-answer-compare-net-revenue-by-store-region-q1-2026] How did total net revenue compare by store region in Q1 2026?
  - Expected reason: compare is an unsupported intent.
- [non-answer-forecast-stockout-days-june-2026] Forecast stockout days for June 2026.
  - Expected reason: forecasting is an unsupported intent.
- [non-answer-stockout-days-by-category-july-2026] What were stockout days by product category in July 2026?
  - Expected reason: time scope is outside the data window (data runs through
    2026-05-31).
- [non-answer-total-net-revenue-yesterday] What was total net revenue yesterday?
  - Expected reason: relative-date phrasing is unsupported (queries need an
    absolute time scope).
- [non-answer-upload-csv-support-tickets-by-priority] Upload this CSV and show support tickets by priority.
  - Expected reason: user-provided CSV files are not supported data sources.

## Conversational Variants

Use these to test terse, casual, or incomplete phrasing users might type in
Slack.

- [variant-net-rev-by-store-region-q1] net rev by store region q1
- [variant-gross-revenue-by-channel-march] gross revenue by channel in march
- [variant-discount-by-promo-code-april] discount by promo code april
- [variant-orders-by-fulfillment-status-may] orders by fulfillment status may
- [variant-net-revenue-by-customer-segment-all-time] net revenue by customer segment all time
- [variant-web-revenue-q1] web revenue q1
- [variant-orders-by-shipping-region-april] orders by shipping region april
- [variant-net-revenue-by-day-march] net revenue by day in march
- [variant-margin-by-category-march] margin by category march
- [variant-line-revenue-by-brand-q1] line revenue by brand q1
- [variant-units-sold-by-subcategory-april] units sold by subcategory april
- [variant-units-returned-by-category-may] units returned by category may
- [variant-margin-by-brand-all-time] margin by brand all time
- [variant-line-revenue-except-electronics-march] line revenue except electronics march
- [variant-customers-by-segment] customers by segment
- [variant-customers-by-loyalty-tier] customers by loyalty tier
- [variant-customers-by-acquisition-channel] customers by acquisition channel
- [variant-customers-by-region] customers by region
- [variant-customers-joined-jan] how many customers joined in jan
- [variant-stores-by-region] stores by region
- [variant-stores-by-channel] stores by channel
- [variant-products-by-category] products by category
- [variant-products-by-brand] products by brand
- [variant-tickets-by-issue-april] tickets by issue in april
- [variant-tickets-by-priority-may] tickets by priority may
- [variant-tickets-by-status-all-time] tickets by status all time
- [variant-tickets-by-issue-excluding-resolved] tickets by issue excluding resolved
- [variant-stockout-days-by-category-may] stockout days by category may
- [variant-on-hand-units-by-category-may] on hand units by category may
- [variant-stockout-days-by-subcategory-april] stockout days by subcategory april
- [variant-on-hand-units-by-store-may] on hand units by store may
- [variant-best-channel-by-gross-revenue] best channel by gross revenue
- [variant-apparel-sales-march] apparel sales march
- [variant-most-returned-category] most returned category
- [variant-units-sold-except-electronics] units sold except electronics
- [variant-new-customers-by-acquisition-channel-this-year] new customers by acquisition channel this year
- [variant-top-loyalty-tier-by-customer-count] top loyalty tier by customer count
- [variant-stores-opened-before-2024] stores opened before 2024
- [variant-stores-not-in-west] stores not in west
- [variant-open-vs-resolved-tickets] open vs resolved tickets
- [variant-high-priority-tickets-april] high priority tickets april
- [variant-biggest-support-issue] biggest support issue
- [variant-tickets-excluding-resolved] tickets excluding resolved
- [variant-outdoor-stockouts-may] outdoor stockouts may
- [variant-which-product-has-most-inventory] which product has most inventory
- [variant-yesterday-net-revenue] yesterday net revenue

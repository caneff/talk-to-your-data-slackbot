# Commerce QA Questions

Use these questions to evaluate the standard Commerce dataset. The dataset covers
orders and customers, with data refreshed through 2026-01-31.

## Revenue

- What was total revenue by region in January 2026?
- What was total revenue by region in Q4 2025?
- What was total revenue in the Northeast region in January 2026?
- What was total revenue in the West region for all time?
- How did total revenue compare by region for all time?

## Order Activity

- What was total revenue by order date in January 2026?
- What was total revenue on January 15, 2026?
- What was total revenue excluding the West region in January 2026?
- What was total revenue for orders before January 2026?
- What was total revenue for orders after January 1, 2026?

## Customers

- What was customer count by customer region in January 2026?
- What was customer count by customer region for all time?
- How many customers were created in January 2026?
- How many customers were created in the Northeast region?
- What was customer count excluding the International customer region?

## Edge Cases

- What was total revenue by customer region in January 2026?
- What was customer count by region in January 2026?
- What was average order value by region in January 2026?
- What was total revenue by product category in January 2026?
- What was total revenue yesterday?

## Known Non-Answer Cases

These should return Non-Answers rather than guessed results.

- What was total revenue?
  - Expected reason: missing time scope.
- What was customer count?
  - Expected reason: missing time scope.
- What was total revenue by customer region in January 2026?
  - Expected reason: no single Dataset Table has both `total revenue` and
    `customer region`.
- What was customer count by region in January 2026?
  - Expected reason: no single Dataset Table has both `customer count` and
    `region`.
- What was average order value by region in January 2026?
  - Expected reason: `average order value` is not a defined metric.
- What was order count by region in January 2026?
  - Expected reason: `order count` is not a defined Commerce metric.
- What was total revenue by product category in January 2026?
  - Expected reason: `product category` is not in the Commerce dataset.
- What was total revenue by region and customer region in January 2026?
  - Expected reason: multi-table or multi-grouping shape is unsupported.
- Which region had the highest total revenue in January 2026?
  - Expected reason: rank is an unsupported intent.
- Which customer region had the highest customer count?
  - Expected reason: rank is an unsupported intent.
- Which region made most money in January?
  - Expected reason: rank is an unsupported intent.
- Biggest customer region?
  - Expected reason: rank is an unsupported intent.
- Use this CSV and tell me revenue by region.
  - Expected reason: user-provided CSV files are not supported data sources.
- Forecast total revenue for February 2026.
  - Expected reason: forecasting is an unsupported intent.

## Conversational Variants

Use these to test terse, casual, or incomplete phrasing users might type in
Slack.

- revenue by region jan 2026
- how much money did we make in jan
- northeast revenue last month
- show west revenue all time
- compare regions by revenue
- revenue trend by day in jan
- revenue on jan 15
- rev minus west
- before january, how much revenue
- after jan 1 revenue
- customers by region
- customer count jan
- how many new customers in january
- northeast customer count
- customers not international
- can we do revenue by customer region?
- avg order value by region
- revenue by product category
- yesterday revenue

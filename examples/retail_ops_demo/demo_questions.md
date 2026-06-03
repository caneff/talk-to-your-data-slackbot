# Retail Operations Demo Questions

Use this artifact to rehearse issue #101 and keep the live demo prompts stable.
All questions below are chosen for the current Retail Operations demo Semantic
Layer and seed data.

## Runtime Command

```bash
uv run python -m data_assistant.slack.runtime_main --semantic-layer-path examples/retail_ops_demo/semantic_layer --duckdb-path :memory: --seed-sql-path examples/retail_ops_demo/seeds/retail_ops_seed.sql
```

Do not run live Slack or live OpenAI as part of this artifact. Manual live
rehearsal remains a separate human step.

## Ground Rules

- Use exact metric names from the Semantic Layer.
- Avoid generic `revenue` wording when both `total net revenue` and
  `total line revenue` exist.
- Treat these as demo rehearsal targets. Live Slack/OpenAI rehearsal remains a
  separate step.

## Assistant Suggested Prompt Set

Use these exact prompts for Assistant suggested prompts:

- `What was total net revenue by store region in Q1 2026?`
- `What was total net revenue by store region?`
- `Which region had the highest total net revenue in Q1 2026?`

## Demo Beats

### 1. Grounded answer with Trust Summary

Suggested prompt:

`What was total net revenue by store region in Q1 2026?`

Expected shape:

- Dataset Table: `demo_orders`
- Metric: `total net revenue`
- Group-by field: `store region`
- Time field: `order date`
- Time range: `2026-01-01` through `2026-03-31`
- Demo data total to expect: `$486,277.25`

### 2. Refusal for unspecified Time Scope

Suggested prompt:

`What was total net revenue by store region?`

Expected shape:

- Returns Non-Answer clarification instead of silent all-time answer
- Asks for time period or explicit all-time confirmation
- No `DataAssistantRun` is produced

### 3. Won't-fabricate / visible degradation beat

Suggested prompt:

`Which region had the highest total net revenue in Q1 2026?`

Expected shape:

- Returns Non-Answer for unsupported intent
- Demonstrates current v1 limit on rank / top-N questions
- No fabricated winner is returned

## Additional Locked Answerable Questions

### Gross margin by product category

Suggested prompt:

`What was gross margin by product category in March 2026?`

Expected shape:

- Dataset Table: `demo_order_lines`
- Metric: `gross margin`
- Group-by field: `product category`
- Time field: `order date`
- Time range: `2026-03-01` through `2026-03-31`
- Demo data total to expect: `$112,882.65`

### Support ticket count by issue category

Suggested prompt:

`What was support ticket count by issue category in April 2026?`

Expected shape:

- Dataset Table: `demo_support_tickets`
- Metric: `support ticket count`
- Group-by field: `issue category`
- Time field: `ticket created date`
- Time range: `2026-04-01` through `2026-04-30`
- Demo data total to expect: `90`

## Rehearsal Notes

- Load Semantic Layer from `examples/retail_ops_demo/semantic_layer`.
- Seed DuckDB from `examples/retail_ops_demo/seeds/retail_ops_seed.sql`.
- Keep prompt wording aligned with current v1 limits: one metric, one group-by
  field, explicit time scope for answerable prompts, no joins, no rank/top-N
  answer until issue #102 lands.

## Skipped Manual Step

Live Slack and live OpenAI rehearsal intentionally skipped for this issue.

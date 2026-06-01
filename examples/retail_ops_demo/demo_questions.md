# Retail Operations Demo Questions

Use this artifact for offline, deterministic rehearsal of issue #101. All
questions below are locked to the current Retail Operations demo Semantic Layer
and seed data.

## Runtime Command

```bash
uv run python -m data_assistant.slack_runtime --semantic-layer-path examples/retail_ops_demo/semantic_layer --duckdb-path :memory: --seed-sql-path examples/retail_ops_demo/seeds/retail_ops_seed.sql
```

Do not run live Slack or live OpenAI as part of this artifact. Manual live
rehearsal remains a separate human step.

## Ground Rules

- Use exact metric names from the Semantic Layer.
- Avoid generic `revenue` wording when both `total net revenue` and
  `total line revenue` exist.
- If a prompt below says verified, that means repo-local deterministic coverage
  against seeded DuckDB data, not live-provider behavior.

## Demo Beats

### 1. Grounded answer with Trust Summary

Suggested prompt:

`What was total net revenue by store region in Q1 2026?`

Verified shape:

- Dataset Table: `demo_orders`
- Metric: `total net revenue`
- Group-by field: `store region`
- Time field: `order date`
- Time range: `2026-01-01` through `2026-03-31`
- Deterministic total: `$486,277.25`

### 2. Refusal for unspecified Time Scope

Suggested prompt:

`What was total net revenue by store region?`

Verified shape:

- Returns Non-Answer clarification instead of silent all-time answer
- Asks for time period or explicit all-time confirmation
- No `DataAssistantRun` is produced

### 3. Won't-fabricate / visible degradation beat

Suggested prompt:

`Which region had the highest total net revenue in Q1 2026?`

Verified shape:

- Returns Non-Answer for unsupported intent
- Demonstrates current v1 limit on rank / top-N questions
- No fabricated winner is returned

## Additional Locked Answerable Questions

### Gross margin by product category

Suggested prompt:

`What was gross margin by product category in March 2026?`

Verified shape:

- Dataset Table: `demo_order_lines`
- Metric: `gross margin`
- Group-by field: `product category`
- Time field: `order date`
- Time range: `2026-03-01` through `2026-03-31`
- Deterministic total: `$112,882.65`

### Support ticket count by issue category

Suggested prompt:

`What was support ticket count by issue category in April 2026?`

Verified shape:

- Dataset Table: `demo_support_tickets`
- Metric: `support ticket count`
- Group-by field: `issue category`
- Time field: `ticket created date`
- Time range: `2026-04-01` through `2026-04-30`
- Deterministic total: `90`

## Deterministic Rehearsal Notes

- Load Semantic Layer from `examples/retail_ops_demo/semantic_layer`.
- Seed DuckDB from `examples/retail_ops_demo/seeds/retail_ops_seed.sql`.
- Drive `workflow_runner.run_data_assistant(...)` with fake Question
  Interpreter proposals for locked answerable prompts.
- Keep this artifact aligned with deterministic tests before changing prompt
  wording.

## Skipped Manual Step

Live Slack and live OpenAI rehearsal intentionally skipped for this issue.

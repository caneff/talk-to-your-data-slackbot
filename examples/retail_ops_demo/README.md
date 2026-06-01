# Retail Operations Demo Dataset

This is a larger demo-only dataset for showing the assistant against richer
business context. It is intentionally outside `semantic_layer/` and `src/` so
the regular test suite does not load it as the default app dataset.

## Contents

- `semantic_layer/`: standalone Semantic Layer YAML for the Retail Operations
  dataset.
- `seeds/retail_ops_seed.sql`: complete DuckDB seed script that creates and
  fills seven demo tables.
- `demo_questions.md`: locked prompts and deterministic rehearsal notes for the
  issue #101 demo flow.

The seed script generates deterministic synthetic data:

- 8 stores
- 360 customers
- 96 products
- 1,800 orders
- 5,400 order lines
- 520 support tickets
- 6,144 inventory snapshot rows

## Start The Slack Bot

Run the normal Slack runtime with custom data locations:

```bash
uv run python -m data_assistant.slack_runtime --semantic-layer-path examples/retail_ops_demo/semantic_layer --duckdb-path :memory: --seed-sql-path examples/retail_ops_demo/seeds/retail_ops_seed.sql
```

Required `.env` values are the same as the base Slack runtime:

- `SLACK_BOT_TOKEN`
- `SLACK_APP_TOKEN`
- `OPENAI_API_KEY`
- optional `OPENAI_MODEL`

The `:memory:` DuckDB location keeps the demo ephemeral. Use a file path for
`--duckdb-path` if you want a persistent local DuckDB file.

## Load The Semantic Layer Manually

```bash
uv run python -c "import pathlib; from data_assistant.semantic_layer.loader import load_semantic_layer; layer = load_semantic_layer(pathlib.Path('examples/retail_ops_demo/semantic_layer')); print(len(layer.datasets), len(layer.tables))"
```

## Create The DuckDB Demo Data Manually

```bash
uv run python -c "import duckdb; con = duckdb.connect('examples/retail_ops_demo/retail_ops.duckdb'); con.execute(open('examples/retail_ops_demo/seeds/retail_ops_seed.sql', encoding='utf-8').read()); con.close()"
```

Example questions this dataset is meant to support:

- What was total net revenue by store region in Q1 2026?
- What was gross margin by product category in March 2026?
- What was support ticket count by issue category in April 2026?
- Which product categories had the most stockout days in May 2026?

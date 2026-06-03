# Version Semantic Layer Config in Repo

For v1, Semantic Layer definitions will live as versioned configuration in this
repo (originally at `semantic_layer/datasets/*.yaml`; see Amendment below for the
current location), rather than in a database UI or
external semantic service. This keeps dataset definitions, metrics, joins,
permissions, and example questions reviewable with the
application code while leaving room to move to dbt metadata or a dedicated
service later.

## Amendment (2026-06-02, #131)

The original decision stands: Semantic Layer config is versioned in this repo. The
config dir has moved from the repo root to `examples/commerce_smoke/semantic_layer/`.
Commerce is now framed as an *example* layer — not a privileged or production
config — living alongside other examples (e.g. `examples/retail_ops_demo/`). A
no-arg `load_semantic_layer()` default still exists for zero-config library and
test loads; it now resolves to the relocated path. A follow-up (#132) introduces a
two-tier default in which the app run loads the retail layer while library/test
loads keep the Commerce example.

### Two-tier default (#132)

There are now two distinct "default layer" tiers, and they intentionally differ:

- **Library / test default** — `DEFAULT_SEMANTIC_LAYER_PATH` in
  `semantic_layer/loader.py` stays `examples/commerce_smoke/semantic_layer`. It
  backs zero-config library loads, `conftest`, the canonical question, the
  `StaticQuestionInterpreterProvider`, `live_eval`, and the workflow runner
  default — all of which assume the Commerce `orders(region, revenue,
  order_date)` schema.
- **App-run default** — a no-flag run of `slack_runtime` (and therefore the
  Docker `CMD`) plus `slack_qa_driver` load the **retail** layer
  (`examples/retail_ops_demo/semantic_layer`), seed the retail demo data, and
  use an in-memory DuckDB. The retail paths live as shared constants in
  `slack_runtime` (`RETAIL_SEMANTIC_LAYER_PATH`, `RETAIL_SEED_SQL_PATH`,
  `RETAIL_DUCKDB_PATH`) — one source of truth that `slack_qa_driver` consumes.
  Explicit `--semantic-layer-path` / `--duckdb-path` / `--seed-sql-path` flags
  still override the retail default.

Keeping the library default on Commerce avoids breaking the suite (the static
provider and canonical question are Commerce-shaped); the retail default is an
app-run concern only.

# Test Data Is Code-Built and Text-Seeded, Not a Committed DuckDB File

## Status

Accepted

## Context

`local_orders_fixture.py` builds an in-memory DuckDB connection, creates the
`orders` schema in code, and inserts caller-provided rows. It is hardcoded to a
single orders-shaped tuple (`OrderRow = (order_date, region, revenue)`), so the
`customers` table and `customer_count` metric defined in the Semantic Layer have
no data behind them.

Widening to more tables and metrics raises an obvious question: rather than
generating data in code, why not commit an actual `.duckdb` file and open it?
A single realistic file would scale to many tables and be explorable with the
DuckDB CLI.

## Decision

Test data stays code-built: a general multi-table in-memory builder where each
test declares the tables and rows it needs inline. Where hand-written row
literals become unwieldy (notably the demo spine), data lives in a **text seed**
— CSV or SQL loaded into DuckDB at startup — not a binary `.duckdb` file.

The fixture is not derived from the Semantic Layer it helps validate: tests
author their own schemas and rows so a schema or type bug in the loader cannot
be masked by building the test data from the same definition.

## Consequences

Test data changes show up as readable diffs in review, which matters because the
data determines the asserted output — the demo deliberately feeds `None` region
and `None` revenue rows to exercise quality-note copy, and a reviewer must see
that. Each test keeps its own tailored dataset next to its assertions rather
than sharing one global database. The builder and seed are version-robust:
no on-disk DuckDB storage format to migrate across DuckDB upgrades.

This data path is for the demo, tests, and local dev only; it is explicitly not
a production data-loading layer, and a committed file would never graduate to
production retrieval regardless.

## Alternatives considered

- **Commit a binary `.duckdb` file.** Rejected: binary blobs in git give opaque
  diffs and unresolvable merge conflicts for data that drives asserted output;
  a single shared database couples tests together and removes per-test data
  tailoring; and the on-disk format is coupled to DuckDB versions.
- **Derive the fixture schema from the Semantic Layer YAML.** Rejected for now:
  building test data from the same definition the pipeline reads is circular and
  can hide loader/schema mismatches. Revisit only if schema duplication becomes
  a real maintenance cost.

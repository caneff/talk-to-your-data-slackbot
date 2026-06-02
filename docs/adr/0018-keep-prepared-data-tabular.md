# Keep Prepared Data Tabular

Status: Accepted

**Prepared Data** remains a tabular `pandas.DataFrame` at the workflow contract for now, rather than being replaced by local row dataclasses. Grouped metric answers are naturally table-shaped: `Data Preparation` produces bounded rows, the **Reasoning Layer** computes grounded slots from those rows, the **Response Composer** renders the grouped values, and the **Interaction Log** records only the sanitized shape plus tiny `key_data` headline rows.

## Considered Options

- **Replace Prepared Data with typed row dataclasses.** Rejected: this mostly re-implements pandas with less capability while still needing table ordering, row counts, totals, first-row ranking, and row serialization. It also creates a broad rewrite across **Data Preparation**, **Reasoning Layer**, **Response Composer**, **Slack Runtime Adapter**, and tests without enough leverage.
- **Add a temporary bridge over the DataFrame.** Rejected for now: it reduces some pandas reads but leaves two parallel result interfaces, which is a half-finished seam unless followed immediately by a larger migration.
- **Keep the DataFrame and deepen request/result semantics elsewhere.** Chosen: future Top-N or multiple-dimension work should make ranking, ordering, limits, and output shape explicit in **Data Request** and **Data Preparation**, not replace the tabular result with a weaker local container.

## Consequences

Pandas is allowed to cross the **Prepared Data** seam because the result is intentionally tabular, not because every caller should invent its own semantics. If duplication grows, deepen around named retrieval semantics such as ranking, ordering, limit, result shape, and table rendering. Do not re-suggest typed row replacement merely to remove pandas from the interface.

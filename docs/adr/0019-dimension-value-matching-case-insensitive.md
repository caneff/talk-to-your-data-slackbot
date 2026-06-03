# Dimension-Value Matching Is Case-Insensitive

## Status

Accepted

## Context

Live-eval case #37 (`ticket_count_high_priority_april`, "high priority")
surfaced a real bug. The model proposes the filter value `('high',)`, but the
seeded dimension values are `High / Low / Medium / Urgent`. A case-sensitive
SQL comparison (`where priority in ($v)`) matches zero rows, so a perfectly
reasonable question silently returns an empty answer.

The first instinct was to resolve provider-proposed values to the catalog's
canonical casing in `promotion.py`. That is not possible: **the catalog stores
no value enum.** A `SemanticField` is `field_id / label / source_column /
data_type / operations` only (see `semantic_layer/schema.py`). The set of
allowed dimension values lives solely in the database, never in the Semantic
Layer config, so there is nothing for the interpreter or promotion step to
canonicalize against.

Two facts shape the decision:

- **Model casing is unreliable.** The LLM emits whatever casing the user typed
  or whatever it normalizes to; this carries no business meaning.
- **Casing never changes which rows match.** `'high'` and `'High'` denote the
  same dimension value. Treating them differently only produces zero-row
  surprises on casing drift — it never protects against a genuinely wrong
  value.

This is the dual of ADR-0008: the interpreter owns *typing* untrusted provider
output at the trust boundary (date / decimal / string), but typing a string
value does not constrain its casing. Casing is a retrieval-time concern, not a
type-validation concern.

## Decision

**Dimension-value casing is immaterial.** This principle is realized in two
coupled spots, with no new catalog state:

1. **Query layer — `data_preparation._filter_sql`.** For `ValuesFilter`s on
   **STRING-typed** fields only (`schema.DataType.STRING`), render
   case-insensitive matching: `where lower(col) in (lower($v), ...)` for
   INCLUDE and `where lower(col) not in (...)` for EXCLUDE. Date and decimal
   `ValuesFilter`s and the `RangeFilter` branch stay exact. Values remain
   bound query parameters — only `lower(...)` is interpolated, never the value
   itself, preserving the parameter-binding contract that ADR-0008 affirms.

2. **Eval comparison — `live_eval`.** The `_append_field_operation_mismatch`
   value comparison casefolds string values (preserving tuple order) so a
   casing-only difference such as `('High',)` vs `('high',)` is not flagged as
   a meaning mismatch. Every other attribute (`operation`, `field`, `lower`,
   `upper`) stays exact, and a genuine value *difference* (`('high',)` vs
   `('urgent',)`) still flags.

## Consequences

Casing-only filter-value differences no longer produce zero-row answers or
spurious eval failures. The fix adds no catalog value enum and no new
canonicalization layer; the database remains the single source of truth for
which dimension values exist.

The tradeoff is against strict matching. Strict matching would surface a value
typed with the wrong casing as "no such value", but at the cost of
reintroducing the zero-row surprise whenever the model's casing drifts from the
stored data. Because casing never changes which rows a value denotes, the
case-insensitive default is the safer behavior. If a future dataset ever needs
case-sensitive dimension values, that is a deliberate change that supersedes
this ADR rather than a default to preserve.

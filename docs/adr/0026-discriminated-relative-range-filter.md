# Interpreter Discriminates Relative Windows On The Range Filter

## Status

Accepted

Amends ADR-0025. The separate top-level `relative_window` field that ADR-0025
introduced is replaced by a `source` discriminator on the `range_filter`
operation. The window convention (ADR-0024) and the division of labor — model
classifies, interpreter computes — are unchanged; only the proposal shape that
carries the classification moves.

## Context

ADR-0025 closed the quarter gap at the root by taking relative-date arithmetic
away from the model: the model would *classify* an `as_of`-anchored phrase into a
structured `relative_window { field, unit, count }`, and the interpreter would
*compute* the calendar window from `as_of_date`. The design was sound. The
shape was not adopted.

`relative_window` was a new optional top-level proposal field, mutually exclusive
with `range_filter`. The scoped paid live eval went 0/7: at temperature 0 the
model ignored the new field on every relative case and instead emitted a
`range_filter` in `field_operations` with `relative_window: null` — the same slot
it already uses for "January 2026". This is not flaky sampling; it is a
deterministic adoption failure. The root cause is the separation itself. The
model has a familiar, well-exercised slot — a `range_filter` in the operations
list — and the `operation` field description still said "range_filter for ...
date ranges." Asking the model to abandon that slot for a foreign top-level field
it has no prior for is a switch it would not make. The separate field was
*ignorable*, so it was ignored.

There is nothing to fix in the arithmetic or the convention. What has to change
is *where the relative-vs-explicit distinction lives in the proposal* so the
model annotates the slot it already fills rather than reaching for a new one.

## Decision

**Carry the relative-vs-explicit distinction as a `source` discriminator on the
`range_filter` operation, not as a separate field.** A date `range_filter` is
either explicit or relative:

- `source = "explicit"` (the default) — the model resolved the window to concrete
  `lower`/`upper` dates, exactly as today.
- `source = "relative"` — the model classifies the `as_of`-anchored phrase by
  carrying `unit` + `count` and leaving `lower`/`upper` null; the interpreter
  computes the window from `as_of_date`.

The model stays in the slot it already uses. Annotating a `range_filter` it was
already going to emit is a far smaller ask than switching to a top-level field,
so the adoption friction that sank ADR-0025's shape is removed by construction.

### The interpreter still computes the window

When a `range_filter` is `relative`, the interpreter ignores any model dates,
reads `as_of_date`, and computes `(lower, upper)` deterministically via the same
ADR-0024 convention and the same code (`compute_relative_window`) ADR-0025
introduced. The output is a typed `RangeFilter` on the named date field —
identical to what an explicit `range_filter` resolves to (ADR-0008). The model
does no relative-date arithmetic; the quarter prior never touches the answer.

### Soundness without re-parsing question text

This was ADR-0025's whole point and it is preserved. "last quarter" arrives as
`range_filter { source: "relative", unit: "quarter", count: 1 }` and the
interpreter snaps to Q1; explicit "Q2 2026" arrives as
`range_filter { source: "explicit", lower: 2026-04-01, upper: 2026-06-30 }` and
is left alone. The two resolve to indistinguishable date ranges, but the
`source` discriminator carries the relative-vs-explicit distinction
*structurally*. The interpreter never re-parses the question text to decide which
one was meant — that brittleness, which the structured proposal exists to remove,
stays removed. The distinction simply moved from "which top-level field is
populated" (ADR-0025) to "which `source` the `range_filter` declares."

### What stays explicit

Only `as_of`-anchored phrases use `source = "relative"`: yesterday, last N days,
last month, last M months, last quarter, last M quarters. Everything the model
already resolves correctly stays a `source = "explicit"` `range_filter`:

- explicit month/year ("January 2026"),
- explicit quarter ("Q2 2026"),
- open-ended explicit bounds ("before January 2024"),
- bare-month resolution against `as_of_date` (ADR-0021).

`explicit` is the default, so non-date operations (group_by, include, exclude)
and explicit date ranges are unaffected. The conflicting `operation` description
that defaulted relative phrases to an explicit range is corrected so a relative
phrase is no longer pulled into the explicit slot.

### What is removed

ADR-0025's separate `relative_window` proposal field is removed, along with its
mutual-exclusion rule with `range_filter` and the validation path that resolved
it. The pure date-math module and its tests are unchanged and reused — only the
proposal shape and the validation entry point change.

## Consequences

The quarter gap stays closed at the root — the model still does no relative
arithmetic — but now via a shape the model actually fills. The fix that
ADR-0025 made *correct* this ADR makes *adopted*, by removing the adoption
friction of a foreign field.

The relative-vs-explicit disambiguation remains sound by construction. It is
carried by the `source` discriminator on the operation rather than by which
top-level field is set, so the interpreter still never guesses whether a Q2
window meant "last quarter" or "Q2 2026."

This is the natural sibling of ADR-0008 and ADR-0021, as ADR-0025 was. As in
ADR-0008, Provider Proposal Validation types and owns the untrusted operation: a
`relative` `range_filter` is one more structured proposal the interpreter
validates, and the window it computes is just another typed date `range_filter`
downstream. As in ADR-0021, `as_of_date` is static configuration the interpreter
reads (ADR-0021's anchor), not data it trusts from the model — the model supplies
only the `{unit, count}` classification, never a date.

The surface is smaller than ADR-0025's: instead of a new top-level field plus a
mutual-exclusion rule, the change is three discriminated fields on an operation
the model already emits, plus the same deterministic computation. ADR-0024 owns
the meaning of a relative window and its pinned example ranges; both are
unchanged. This document locks the shape; the schema, prompt, and tests land in
the implementation that follows #258.

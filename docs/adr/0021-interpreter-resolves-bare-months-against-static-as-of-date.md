# Interpreter Resolves Bare Months Against A Static As-Of Date

## Status

Accepted

## Context

The Question Interpreter receives no reference or "as-of" date. Terse Data
Questions that name a bare month with no year — live-eval cases #50
(`terse_tickets_by_priority_may`) and #51 (`terse_stockout_days_by_category_may`),
both phrased like "tickets by priority may" — cannot be resolved to the right
year. The interpreter has every other ingredient (it already turns an explicit
"January 2026" into a full-month `range_filter` on the selected metric's own
date field), but it has no time anchor to choose the year for a bare month.

The interpreter needs a "today" to resolve the bare month against. Three sources
were considered:

- **`date.today()` (system clock).** Rejected. It time-bombs the eval: the
  correct year drifts as wall-clock time passes, so a case that expects
  `MAY_2026` would silently start failing once the calendar advances.
- **Data-max (the latest date present in the seed).** Rejected. The seeded data
  maxes out at 2026-01-31, so "may" would resolve to May *2025* — the wrong
  year, and not the demo's notional present.
- **A static configured `as_of_date`.** Chosen. It is deterministic (the eval
  never drifts) and demo-coherent (it represents the demo's notional "today",
  independent of when the seed happens to end).

The resolution rule must be unambiguous for any bare month, not just May, so it
is stated as *most-recent occurrence on-or-before the as-of date*: if the named
month is on-or-before the as-of date's month, use the as-of year; if it is a
later month, use the prior year.

## Decision

**Author a single static `as_of_date` in the dataset YAML and resolve bare
months against it.** Realized across four wiring surfaces:

1. **Schema owns validation.** `CuratedDataset` gains an optional
   `as_of_date: datetime.date | None = None` field. The YAML scalar
   `2026-06-30` is parsed to a real `datetime.date` by `model_validate`
   (`yaml.safe_load` already yields a `date`). Optional with default `None`
   keeps every existing dataset, fixture, and test green.

2. **Dataset YAML owns the value.** `retail_ops.yaml` declares
   `as_of_date: 2026-06-30` once, alongside `dataset_id` / `name`. The value is
   `2026-06-30`: it covers every demo `example_question` (Q1 / March / April /
   May 2026) and is tighter than `2026-12-31`, so it still discriminates a
   wrong-direction resolution bug.

3. **Context owns transport.** `build_semantic_layer_context` emits a top-level
   `as_of_date` as an **ISO string** (not a `date` object — the provider
   `json.dumps`-es the context, which raises on a raw `datetime.date`). One
   "today" for the run, not per-dataset. When no dataset carries an
   `as_of_date`, the key is **omitted entirely** (not null), leaving the rule
   dormant and the old behavior intact.

4. **Developer prompt owns the rule.** A bare-month rule in `## Dates` resolves
   the named month to the most recent occurrence on-or-before `as_of_date`, then
   emits a full-month `range_filter` on the selected metric's own compatible
   date field — reusing the metric's-own-date-field machinery already in the
   prompt rather than restating it. One worked example anchors it.

## Consequences

Bare-month Data Questions resolve to the demo's notional present year
deterministically, fixing #50 and #51 without coupling the eval to the wall
clock or to the seed's end date. The behavioral proof is the scoped paid live
eval on cases #50/#51 run after this change; the wiring and dormancy are covered
by free unit tests.

This is the dual of ADR-0008: the interpreter still owns *typing* untrusted
provider output during **Provider Proposal Validation**, and a resolved
bare-month range is just another date `range_filter` that validation types. The
as-of date is configuration the interpreter reads, not data it trusts from the
model.

The tradeoff is that the demo's "today" is now a hand-maintained constant: when
the seed window moves, `as_of_date` must move with it. That is a deliberate
single-line edit in one YAML file, and it is the price of eval determinism — the
alternative sources reintroduce either clock drift or a wrong-year resolution.

# Interpreter Computes Relative Windows From A Model Classification

## Status

Accepted

Amends ADR-0024 for relative date phrases (the window convention itself is
unchanged).

## Context

ADR-0024 locked the meaning of a relative date window — *most recent complete
unit(s), excluding the in-progress unit that contains `as_of_date`* — and asked
the developer prompt to carry that convention as a principle the model applies
when it emits a `range_filter`. The day and month families honor it. Quarters do
not: asked on the last day of Q2, the model returns the in-progress quarter (Q2)
for "last quarter" rather than Q1, across two prompt attempts. Those cases are
the `deferred` set in ADR-0024 and the open gap in #239.

Two prose attempts going 0/3 on quarters is not prompt noise; it is a hard model
prior. The model has a strong intuition that "last quarter" means "the quarter
you are standing in," and stating the boundary rule in the prompt does not move
it. More few-shots would be per-phrasing accretion against a prior the prompt
cannot reach — exactly the kind of fix this repo avoids.

There is a second, deeper problem that prose can never close. ADR-0024 resolves
"last quarter" by snapping back one whole quarter from `as_of_date`. But an
explicit "Q2 2026" resolves to the *same* range. A blind quarter-snap performed
after the model has already chosen a window cannot tell a relative "last quarter"
apart from an explicit "Q2 2026" — the two are indistinguishable once both are a
`range_filter`, and re-parsing the question text to disambiguate would
reintroduce the brittleness the structured proposal was meant to remove. The
relative-vs-explicit distinction has to be carried in the proposal itself, not
recovered from prose.

The stable thing to reason about is *who does the date arithmetic*. If the model
both classifies the phrase and computes the window, its quarter prior leaks into
the answer and the disambiguation is unrecoverable. If the model only classifies
and the interpreter computes, the prior is removed entirely and the distinction
is explicit by construction.

## Decision

**The model classifies a relative phrase into a structured field; the
interpreter computes the calendar window from `as_of_date` deterministically.**
The model does no date arithmetic for relative phrases.

### The new proposal field

A new optional proposal field:

```
relative_window { field: <date label>, unit: "day" | "month" | "quarter", count: int }
```

- `field` names the target date field. Field selection stays with the model,
  where it already works well — the model continues to pick the selected
  metric's own compatible date field, exactly as it does for an explicit
  `range_filter` (ADR-0021).
- `unit` and `count` are the model's *classification* of the phrase: "last
  quarter" is `{unit: "quarter", count: 1}`, "last three months" is
  `{unit: "month", count: 3}`, "yesterday" is `{unit: "day", count: 1}`. No
  dates appear in this field.

`relative_window` is **mutually exclusive** with a model-emitted `range_filter`
on the same proposal. A proposal carries one or the other, never both.

### The interpreter computes the window

Given `relative_window`, the interpreter computes `lower` and `upper` from
`as_of_date` deterministically, enforcing the **ADR-0024 convention in code**:
most-recent-complete unit(s), excluding the in-progress unit that contains
`as_of_date`. The convention is unchanged and is not up for debate here; ADR-0024
remains the source of truth for what a relative window *means* and for the pinned
example ranges. What moves is only *where the arithmetic happens* — out of the
prompt and into the interpreter, where it cannot be derailed by a model prior.

### Disambiguation by which field is populated

Relative-vs-explicit is decided by **which field the model populates**, not by
re-parsing question text:

- `relative_window` → an `as_of`-anchored phrase the interpreter must compute.
- `range_filter` → a window the model already resolved to concrete dates.

This closes the soundness hole. "last quarter" arrives as
`relative_window {unit: "quarter", count: 1}` and the interpreter snaps to Q1;
explicit "Q2 2026" arrives as a `range_filter` covering Q2 and is left alone. A
blind post-hoc quarter-snap could not tell these apart; the populated field
makes the distinction structural.

### What stays a model-emitted `range_filter`

Only `as_of`-anchored phrases use `relative_window`: yesterday, last N days,
last M months, last quarter, last M quarters. Everything the model already
resolves correctly stays a model-emitted `range_filter`:

- explicit month/year ("January 2026"),
- explicit quarter ("Q2 2026"),
- open-ended explicit bounds ("before January 2024"),
- bare-month resolution against `as_of_date` (ADR-0021).

The new field is the smallest wedge that removes the model prior, not a rewrite
of date handling.

### One field, all families

`relative_window` applies to **all relative families** — day, month, and quarter
— for one uniform convention rather than a quarters-only patch. Days and months
already pass under prose, but routing them through the same structured field
keeps a single code path and a single place the ADR-0024 convention is enforced,
so a future relative family inherits the boundary rule for free.

## Consequences

The quarter gap in #239 is closed at the root: the model's "you are standing in
it" prior never touches the answer because the model no longer computes the
window. Removing the arithmetic from the prompt is what makes the fix reliable
where two prose attempts could not.

The relative-vs-explicit disambiguation becomes sound by construction. The
distinction lives in which proposal field is populated, so the interpreter never
has to guess whether a Q2 window was meant as "last quarter" or "Q2 2026."

This amends ADR-0024 for relative phrases only. The window convention — most
recent complete unit(s), excluding the in-progress unit — and its pinned example
ranges are unchanged; ADR-0024 still owns the meaning of the window, and this ADR
only moves the computation that realizes it from the prompt into code.

It is the natural sibling of ADR-0008 and ADR-0021. As in ADR-0008, the
interpreter types and owns untrusted model output during Provider Proposal
Validation: `relative_window` is one more structured proposal the interpreter
validates, and the window it computes is just another typed date `range_filter`
downstream. As in ADR-0021, `as_of_date` is static configuration the interpreter
reads (ADR-0021's anchor), not data it trusts from the model — the model supplies
only the `{unit, count}` classification, never a date.

The cost is a small surface increase: a new optional proposal field, its
mutual-exclusion rule with `range_filter`, and the deterministic window
computation in the interpreter. That surface is the deliberate price of removing
the model prior and making the disambiguation structural rather than textual.
The concrete schema, prompt change, and tests are out of scope for this ADR and
land in the implementation that follows #239; this document locks the design they
realize.

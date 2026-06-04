# Interpreter Resolves Relative Dates Against A Static As-Of Date

## Status

Accepted

## Context

ADR-0021 gave the Question Interpreter a static `as_of_date` (`2026-06-30` for
retail) and a rule for resolving a bare month against it. Relative date phrases —
"yesterday", "last 7 days", "last 30 days", "last month", "last two months",
"last quarter", "last three quarters" — are the natural next class of time
expressions a user types, and they need the same anchor: without a notional
"today" the interpreter cannot turn "last month" into a concrete calendar window.

The interpreter already has every other ingredient. It turns an explicit
"January 2026" into a full-month `range_filter` on the selected metric's own
compatible date field (ADR-0021), and it reads `as_of_date` from
`semantic_layer_context`. What was missing was a single, unambiguous convention
for what a relative window *means* relative to that anchor — one that resolves
every family (day / month / quarter) without per-phrasing special cases, and that
is stable for the eval.

The hard question is the boundary: does "last month" include the partial current
month, and does a window ever include `as_of_date` itself? An ad-hoc answer per
phrase would be unteachable and would drift. The convention below was grilled and
locked so the eval can pin exact ranges.

## Decision

**Resolve relative date phrases against `as_of_date` by one unifying convention,
then emit a full `range_filter` on the selected metric's own compatible date
field** — the same shape and same machinery as the bare-month rule (ADR-0021).

### The unifying convention

A relative window covers the **most recent COMPLETE unit(s)**, **excluding the
in-progress unit that contains `as_of_date`**. `as_of_date` is the notional
*today* and is treated as an incomplete day; the day, month, and quarter that
contain it are all in progress and never appear in a relative window.

### Per-unit formula (unit = day / month / quarter)

- **Day.** Most recent complete day is `as_of − 1` (yesterday).
  - "yesterday" → `(as_of − 1)..(as_of − 1)`.
  - "last N days" → `(as_of − N)..(as_of − 1)` — exactly N days, never including
    `as_of`.
- **Month.** Most recent complete calendar month is the month before
  `as_of`'s month.
  - "last month" → that month (M = 1).
  - "last M months" → lower = first day of `(currentMonth − M)`, upper = last day
    of `(currentMonth − 1)`.
- **Quarter.** Most recent complete calendar quarter is the quarter before
  `as_of`'s.
  - "last quarter" → that quarter (M = 1).
  - "last M quarters" → the same count-back over whole calendar quarters.

### In-progress-unit exclusion edge case

`as_of_date = 2026-06-30` is the *last* day of both June and Q2. Because today is
incomplete, **June and Q2 are the in-progress units and are excluded**: "last
month" = May (not June), "last quarter" = Q1 (not Q2). The `as_of` day itself
never lands in any relative window.

### Example ranges (as_of `2026-06-30`)

| Phrase | Resolved range_filter |
|--------|-----------------------|
| yesterday | `2026-06-29 .. 2026-06-29` |
| last 7 days | `2026-06-23 .. 2026-06-29` |
| last 30 days | `2026-05-31 .. 2026-06-29` |
| last month | `2026-05-01 .. 2026-05-31` |
| last two months | `2026-04-01 .. 2026-05-31` |
| last quarter | `2026-01-01 .. 2026-03-31` |
| last three quarters | `2025-07-01 .. 2026-03-31` |

The rule lives in the developer prompt's `## Dates` section as one principle plus
the formula and at most two lean worked anchors (one rolling-day, one
multi-period calendar), mirroring the single bare-month worked example — not a
per-phrasing few-shot. This repo fixes prompt behavior with an invariance rule,
not per-phrasing accretion.

## Consequences

Relative date phrases resolve to concrete calendar windows deterministically,
anchored to the demo's notional present rather than the wall clock or the seed's
end date — the same determinism ADR-0021 bought for bare months. The behavioral
proof is the scoped paid live eval run after this change; the cases here prove the
expectations are well-formed and validate.

The initial scoped paid live eval confirms the day and month families
("yesterday", "last 7 days", "last month", "last two months"), but the model does
not yet honor the convention for **quarters** — asked on the last day of Q2 it
returns the in-progress quarter (Q2) rather than Q1, across two prompt attempts —
and "last 30 days" flakes by one day. Those three cases are marked `deferred`
(detection gap tracked in the follow-up issue), so the eval reports them as
known-not-yet and tripwires once a fix makes them pass. The convention itself is
unchanged and confirmed correct: any day into a quarter, "last quarter" is the
prior quarter. The gap is model detection, not the boundary rule.

This is the sibling of ADR-0021 and the dual of ADR-0008: there is no new schema
or validation code. A resolved relative window is just another date
`range_filter`, which Provider Proposal Validation already types from untrusted
model output. The `as_of_date` is configuration the interpreter reads, not data it
trusts from the model.

The boundary is hard to reverse once cases pin it. The eval expectations encode
the exact ranges above, so changing the convention later (e.g. including the
in-progress unit, or making "last 7 days" inclusive of `as_of`) would silently
break those pinned cases and any downstream replay that assumes them. The
convention is therefore locked, and "most recent complete unit(s), excluding the
in-progress unit" is the single sentence any future relative family must obey.

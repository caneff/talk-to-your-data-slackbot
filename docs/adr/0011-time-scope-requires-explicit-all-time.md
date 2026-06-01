# Time Scope is explicit; silence is refused, not defaulted to all-time

Every **Data Question** carries a **Time Scope** that is one of three: _bounded_
(a named period — month, range, half-bounded, or single date), _all-time_ (the
team member explicitly asks across every date), or _unspecified_ (no period
given). A _bounded_ scope is fully signaled by the presence of a date-typed
filter operation; _all-time_ requires an explicit `all_time` flag on the
provider proposal; _unspecified_ (no date filter and `all_time` false) returns a
`MISSING_TIME_SCOPE` Non-Answer asking the team member to narrow the period. The
trusted **Question Frame** stores the resolved scope as a `time_scope` enum
(`BOUNDED` | `ALL_TIME`); an _unspecified_ frame never exists because that path
short-circuits to a Non-Answer first.

## Considered Options

We rejected treating "no date filter" as an implicit all-time query. A bounded
query and an unbounded one produce identical SQL when no `WHERE` clause is
emitted, so absent a marker the system cannot tell "the user asked for all time"
apart from "the user forgot to say." Defaulting silence to all-time risks
returning a confidently unbounded answer over a single month of data
(`as_of 2026-01-31`); defaulting it to a refusal is safe but then blocks the
legitimate "for all time" request. Making all-time an explicit, stated choice
resolves both: silence is a **Material Ambiguity** we clarify, and all-time is a
deliberate signal we honor.

## Consequences

- A date filter present together with `all_time=true` is an incoherent proposal
  and is rejected as `INVALID_PROVIDER_OUTPUT`.
- The earlier "missing time range" behavior was faked by a proposal with
  `metric=None`; the real `MISSING_TIME_SCOPE` guard replaces that trick.
- Three previously dead `_time_range_label` branches (`from X`, `through Y`,
  `all available data`) become reachable and require coverage.

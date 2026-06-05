# Drop Deterministic Pre-Provider Rejects in the Question Interpreter

The **Question Interpreter** no longer runs deterministic pre-provider guards
that short-circuit a request before provider classification. Support-boundary
classification now has a single source of truth: provider intent classification
plus the surviving deterministic gates (time scope, metric label, and
provider-output validation). The three removed regex guards
(unsupported-data, rank-intent, and data-availability phrasing) are gone, along
with the `UNSUPPORTED_DATA` and `UNSUPPORTED_AVAILABILITY` reason codes that only
they emitted. `UNSUPPORTED_INTENT` stays, emitted by output validation for
still-deferred intents such as compare, trend, or forecast.

## Considered Options

- **Keep the guards as defense-in-depth (prior state).** A parallel regex layer
  rejected obvious unsupported shapes before spending a provider call and emitted
  tailored reject copy. Rejected: it is a second, divergent source of truth for
  the support boundary that drifts from the provider's actual classification, and
  it couples support policy to brittle phrasing patterns.
- **Keep but narrow the guards.** Shrink the patterns to only the highest-
  confidence phrasings. Rejected: it keeps the dual-source-of-truth problem and
  the maintenance cost while covering less, for marginal benefit.
- **Remove all three guards (chosen).** Let these shapes reach the provider and
  route through the surviving gates or supported path: a rank ask now
  classifies as supported `rank` and continues through deterministic retrieval;
  an unsupported-data ask resolves to a label outside the Semantic Layer
  (`UNKNOWN_SEMANTIC_LABEL`); a data-availability ask that names no explicit
  time scope is rejected by the time-scope gate (`MISSING_TIME_SCOPE`,
  ADR-0011).

## Consequences

- One source of truth for support-boundary classification: provider intent
  classification, not a parallel regex layer that can disagree with it.
- We give up a saved API call on obvious rejects and the tailored
  `UNSUPPORTED_DATA` / `UNSUPPORTED_AVAILABILITY` reject copy; these shapes now
  surface the more generic `UNKNOWN_SEMANTIC_LABEL` / `MISSING_TIME_SCOPE`
  wording.
- No correctness change. Retrieval stays deterministic (ADR-0014), so a
  false-success cannot fabricate numbers, and the surviving gates still reject
  every one of these shapes — coverage moves from guard-fired tests to
  surviving-path Non-Answer tests rather than dropping.
- Supersedes the CONTEXT.md "Unsupported Intent Guard" framing; **Rank Intent**
  is no longer deferred and no longer depends on any deterministic pre-provider
  guard.

# Semantic Router Owns Available Data Resolution

## Status

Accepted

Amends [ADR-0003](0003-short-circuit-ambiguity-with-stage-results.md).

## Context

Resolving a Question Frame to "exactly one Curated Dataset and exactly one
Dataset Table" was split across two modules over the same match set. The
Semantic Router decided dataset cardinality; the Data Requester then re-checked
that exactly one dataset was selected (a dead branch, since the router already
guaranteed it), re-filtered the same matches to find the table, and decided
table cardinality. The "exactly one match" invariant straddled a seam, and the
dead dataset re-check was the leak admitting itself.

Two questions surfaced while deciding the fix:

- Could access act as a tiebreaker among matching datasets ("I can see one of
  the two that match")? Today access is a dataset-level *gate* run after
  resolution, never a *filter* during it.
- Should authorization-aware selection be folded into resolution? Doing so would
  move identity and the access rule into the router, scatter the single
  authorization chokepoint, and risk collapsing `ACCESS_DENIED` ("exists but
  forbidden") into `NO_MATCHING_DATASET` ("no such data") — a distinction
  CONTEXT.md explicitly requires the assistant to preserve.

## Decision

The Semantic Router resolves Available Data all the way down to one canonical
`SemanticMatch` (dataset + table + metric + dimension) or a `NonAnswer`.
Resolution stays layered: dataset cardinality first, then table cardinality
within the chosen dataset. `AvailableDataResolution` carries the resolved match
and keeps the `DatasetSelection` for dataset-grained rationale. The Data
Requester is reduced to formatting a `DataRequest` from the resolved match and
can no longer represent the ambiguous state.

Table-cardinality Non-Answers (`AMBIGUOUS_TABLE`, `NO_MATCHING_TABLE`) are now
emitted by the Semantic Router, so they carry `stage = SEMANTIC_ROUTER`. The
`DATA_REQUESTER` value is removed from `NonAnswerStage`, since no stage produces
it anymore. `stage` has no production consumer (only the Decision Trail and
tests read it), so this is safe; user-facing copy keys on reason code, not stage.

Access remains a separate, downstream, dataset-level gate
(`authorize_dataset_access`). It is the single auditable authorization
chokepoint and continues to return an explicit `ACCESS_DENIED`.

## Consequences

The "exactly one dataset, one table" invariant lives in one module. The match
set stops leaking downstream and the dead dataset re-check is deleted.

Because resolution is now atomic and runs before the access gate, a caller who
both lacks dataset access *and* asks a table-ambiguous question now receives the
table Non-Answer instead of `ACCESS_DENIED` (a precedence flip from access-first
to ambiguity-first). This is acceptable: the ambiguity verdict is
identity-independent and the table messages name no tables, so it discloses no
more than before.

This change overlaps the not-yet-implemented Non-Answer Catalog (ADR-0005) on
`data_requester.py` and `workflow/contracts.py`; whichever lands first, the
table Non-Answers' construction site and stage move to the router.

## Alternatives considered

- **Keep the split, only delete the dead dataset re-check.** Smaller and
  ADR-0003-preserving, but leaves the table decision straddling the seam.
  Rejected: the Data Requester should never have owned cardinality.
- **Fold authorization into selection (access-as-filter).** Would let "match
  several, access one" resolve to an answer, but collapses the
  exists-but-forbidden distinction CONTEXT.md requires, scatters the
  authorization chokepoint, and makes the future Routing Cache identity-keyed.
- **Access-as-tiebreaker inside resolution.** Rejected as incoherent: selecting
  among options by access *is* an authorization decision at selection time, so
  it necessarily moves identity and the access rule into the router — the very
  coupling this ADR keeps out. It is not a tiebreaker; it is relocating
  authorization.

Access-aware selection is therefore deferred, not abandoned. If the
"match several, access one" case proves to bite real users, it should be taken
up deliberately as a redefinition of what the Semantic Router owns (does it own
authorization?), with its own ADR — not smuggled in as a tiebreaker.

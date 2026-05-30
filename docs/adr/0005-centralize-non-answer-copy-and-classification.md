# Centralize Non-Answer Copy and Classification in a Non-Answer Catalog

Every Non-Answer Response is defined in one Non-Answer Catalog keyed on reason
code — its team-member-facing reason, next step, and response kind — and the
Question Interpreter, Semantic Router, Data Requester, and Access Controller
construct Non-Answers through the catalog rather than composing reason text in
place. The `response_kind` is a total function of the reason code (enforced with
`assert_never`), not derived from reason strings or the producing stage; the
Response Composer looks it up from the catalog and owns only sentence rendering.

## Considered Options

- Keep per-stage Non-Answer construction with composer-side classification by
  reason string and stage. Rejected: classification drifted from wording — a
  missing metric rendered "…cannot answer yet" but was classified `unsupported`,
  while a missing time range was `clarification_needed`. Re-deriving meaning from
  exact reason strings and ambiguity tuples coupled wording to classification and
  let the two diverge silently.
- Expose the catalog as a public, enumerable table of definitions. Deferred until
  a real consumer (Decision Trail, Clarification Loop) needs to read it.

## Consequences

- `response_kind` becomes a typed `ResponseKind` on the Final Response; adding a
  reason code without classifying it is a type error, not a runtime surprise.
- `stage` stays on the Non-Answer as informational metadata only. It is not
  derivable from the reason code: `AMBIGUOUS_DATASET` is raised by both the
  Semantic Router and the Data Requester.

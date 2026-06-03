# Render Non-Answer Copy From Structured Non-Answers

A `NonAnswer` carries only structured classification — `reason_code`, `stage`,
the context tuple, and `datasets` — and no longer stores its team-member-facing
`reason` or `next_step` prose. The Non-Answer Catalog remains the single owner of
copy, but that copy is **rendered on demand** from the structured Non-Answer
rather than baked onto each instance at construction. The Response Composer asks
the catalog to render wording for a Non-Answer instead of reading prose fields
off it.

This refines [ADR-0005](0005-centralize-non-answer-copy-and-classification.md):
0005 made the catalog the single owner of copy, but the copy still travelled on
every `NonAnswer` and the composer read it from the instance. Separating the
structured value from its rendering removes that duplication and creates one
seam where wording is produced.

## Considered Options

- Keep `reason`/`next_step` on the `NonAnswer` and freeze exact copy by
  asserting the literal strings everywhere a Non-Answer is produced. Rejected:
  the snapshot, semantic-router, data-requester, and provider tests each
  re-copied catalog prose, so a one-word copy edit broke unrelated tests and the
  strings drifted between copies.
- Adopt snapshot tooling (e.g. `inline-snapshot`) so the exact end-to-end text
  stays machine-maintained on each producing test. Rejected for now: it freezes
  prose in the *interpreter* tests rather than where copy lives, adds a
  dependency, and still mixes "is routing correct" with "is the wording
  approved" in one assertion. Reconsider if a consumer needs full end-to-end
  text snapshots.

## Decisions

- **Non-Answers are pure structured data.** `reason`/`next_step` come off the
  dataclass. Construction stays centralized in the catalog builders.
- **Copy is rendered, owned by the catalog.** A single rendering entry point
  turns a structured Non-Answer into its `reason`/`next_step`; only it knows how
  to interpolate context such as the denied **Curated Dataset** name.
- **Non-Answer context uses the right name.** `NonAnswer.context` and the
  catalog definition context tuple carry rendering labels that are not limited
  to ambiguities. `QuestionFrame.unresolved_ambiguities` stays unchanged because
  it still means actual Question Frame ambiguity.
- **Tests assert structure, not prose.** Routing and contract tests
  (Question Interpreter snapshots, Semantic Router, Access Controller, provider
  tests) assert `reason_code` + `stage` + context, never the sentences.
- **Exact copy is frozen once.** A single golden test over the catalog's
  rendering is the only place literal user-facing strings are pinned. It is the
  intended failure when copy changes, reviewed in one spot.

## Deferred

- **Swappable wording behind a provider seam.** The rendering entry point is
  shaped so it can later become a `NonAnswerWording` boundary (matching the
  provider-boundary style of
  [ADR-0004](0004-defer-llm-orchestration-framework.md)), with the static
  catalog as the default implementation. Not extracted yet — the composer calls
  the catalog renderer directly.
- **LLM-generated wording.** An LLM-backed wording implementation could sit
  behind that seam for user-facing clarifications, with the static catalog copy
  kept as the offline fallback and the developer-facing reason codes (e.g.
  invalid provider output) staying static. Such wording would be graded by an
  eval (the `question_interpreter.live_provider_proposal_eval` pattern), not
  asserted equal.

## Consequences

- `stage` and `reason_code` remain the only meaning a Non-Answer carries, as in
  ADR-0005; the composer still never reads `stage`.
- Producing-stage tests get simpler: they drop copied prose and assert the
  structured outcome, so copy edits no longer ripple across the suite.
- The catalog gains a rendering entry point and a golden copy test; everything
  upstream of the composer stays prose-free.

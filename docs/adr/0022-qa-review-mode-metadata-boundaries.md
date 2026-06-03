# Record QA Review Mode Metadata Boundaries

## Status

Accepted

## Context

**QA Review Mode** runs a curated battery of **QA Case** questions through the
shared assistant path, posts each **Final Response** into Slack, and lets a
maintainer capture **Flags** or notes before marking the response handled. That
workflow needs two durable metadata surfaces beyond the transient Slack thread:

- stable identity for each curated **QA Case**, even when wording changes
- a minimal committed record of each **Known QA Issue**, so repeated failures
  can be recognized as already triaged

PRD #163 split that work into two implementation slices:

- issue #164 added strict `[qa-case-id]` parsing so each **QA Case** has a
  stable maintainer-tooling id
- issue #165 added the committed **Known QA Issue** sidecar plus GitHub prune
  preflight

The boundary matters because several nearby surfaces look convenient but are not
durable source-of-truth metadata:

- Slack thread text is per-run presentation, not stable identity
- the **Interaction Log** captures observed runtime behavior and maintainer
  review context, but it is retention-bounded and append-first
- GitHub issues are durable, but issue search alone cannot safely infer which
  **QA Case** or **Flag** a report belongs to

The repo now has enough implementation to record the intended metadata model
explicitly.

## Decision

**QA Case ids are the durable identity for curated QA questions.** A QA battery
entry is identified by its bracketed id, not by its current wording. Small
question edits may change readability or scope, but the id persists so review
history and **Known QA Issue** mappings survive those edits.

**Known QA Issues live in a committed minimal sidecar file, not in markdown or
runtime logs.** The sidecar is machine-owned JSON committed next to the QA
battery. Its privacy boundary is intentionally narrow: each entry contains only
the **QA Case** id, the GitHub issue number, and the **Flag** category. It does
not carry response text, Slack URLs, maintainer notes, or copied **Interaction
Log** payloads.

**Normal QA runs prune the sidecar before trusting it.** Preflight validates the
sidecar against current **QA Case** ids and prunes entries for closed GitHub
issues or stale ids. That keeps the committed file aligned with both the active
battery and the live issue tracker instead of letting old mappings silently
accumulate.

**`--skip-known-issue-prune` is an explicit escape hatch, not the default
workflow.** It exists for cases where GitHub lookup is unavailable or too slow,
but using it means the run is intentionally operating without the normal
freshness check.

## Rejected Alternatives

**Markdown metadata in the QA battery.** Rejected. Mixing issue numbers and
**Flag** categories into the human-edited markdown battery would make the
question list noisy, invite manual formatting drift, and blur the boundary
between maintainer-readable prompts and machine-owned metadata. The battery is
for curated **QA Case** text; the sidecar is for durable **Known QA Issue**
state.

**Fuzzy GitHub inference from question text or runtime logs.** Rejected.
Inferring a **Known QA Issue** by searching GitHub for similar wording, Slack
messages, or **Interaction Log** content is ambiguous and unstable. Question
wording changes, issue titles drift, and one issue can cover multiple **Flag**
categories or multiple **QA Case** ids. Durable metadata needs an explicit
mapping, not best-effort search.

**Interaction Log as durable Known QA Issue source of truth.** Rejected. The
**Interaction Log** is an improvement corpus and review trail, not authoritative
metadata storage. It is retention-bounded by the **Interaction Log Retention
Policy**, records per-run observations, and may include transient maintainer
notes or repeated **Flags** for the same underlying issue. It remains useful
evidence for triage, but it is not stable enough to define the canonical set of
**Known QA Issues**.

## Consequences

The metadata boundary stays narrow and reviewable:

- **QA Case** ids provide durable identity across wording edits
- the committed **Known QA Issue** sidecar stays minimal and privacy-safe
- GitHub remains authoritative for whether an issue is still open
- the **Interaction Log** remains a runtime evidence trail, distinct from
  durable known-issue metadata

This also sharpens maintainer expectations. Repeated **Flags** in **QA Review
Mode** do not automatically become **Known QA Issues**; they become known only
when explicitly mapped to a GitHub issue in the sidecar. Conversely, a sidecar
entry is not permanent bookkeeping: prune preflight removes stale ids and closed
issues unless the operator explicitly uses `--skip-known-issue-prune`.

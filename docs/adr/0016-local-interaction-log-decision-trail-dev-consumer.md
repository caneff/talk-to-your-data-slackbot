# Local Interaction Log as the Decision Trail's dev consumer

Status: Accepted

Every **Data Question** handled by the Slack Assistant Adapter will append one
structured JSON line to a gitignored, append-only **Interaction Log** at
`logs/interactions.jsonl`. The record carries the question, the response, latency,
the model, and — for answers — the **Question Frame**, the routed Data Request,
the **Prepared Data** *shape* (rows × columns) plus quality notes, and the tiny
`key_data` headline numbers. The Interaction Log is the local-dev consumer the
roadmap's deferred **Decision Trail** was waiting for: a maintainer pastes any
logged interaction into Claude Code when asking for an improvement. There is no
UI in this slice (the **Flag** button UI is a later slice); records always write
`flags: []`.

## Considered Options

- **Defer the Decision Trail entirely.** On the roadmap, but it was waiting for a
  concrete consumer. Rejected: the maintainer's "paste me an interaction and
  improve it" workflow is exactly that consumer, and waiting longer keeps the
  trail abstract.
- **Append-only JSONL (chosen).** One `json.dumps(record)` line per request,
  greppable and diffable, owned by a flat `interaction_log` module that holds all
  file I/O and the schema. Cheap to write, trivial to paste, and a natural fit
  for a local dev trail.
- **A binary store (cf. ADR-0010).** Rejected for the same reason ADR-0010
  rejected a binary fixture: a text stream the maintainer (and Claude Code) can
  read and diff beats an opaque file for a local debugging artifact.

## Consequences

- The Interaction Log deliberately includes the tiny `key_data` cell values that
  the glossary **Decision Trail** excludes. This is justified by its consumer:
  local correctness debugging needs the headline numbers. It is gitignored and
  never shipped. Bulk **Prepared Data** cell values and secrets are still
  excluded — only the shape, quality notes, and `key_data` headline rows are
  recorded. The **Question Frame** and metric expression are kept as debug signal.
- Capture lives at the **Slack Assistant Adapter** (`on_user_message`), which
  already holds the full result, latency, and user in scope. The pure pipeline
  runner stays I/O-free, so the demo, tests, and evals never write logs.
- A new optional `FinalResponse.non_answer` field (backward-compatible, default
  `None`, populated by `compose_non_answer_response`) lets non-answer records
  record the fine 15-way `reason_code` + `stage` instead of the coarse 4-bucket
  `ResponseKind`.
- A logging failure never breaks the user reply: the append is wrapped so the
  user-facing `say` always wins.
- Reversing later means deleting the `interaction_log` module, the adapter
  capture, and the optional `FinalResponse.non_answer` field; nothing else
  depends on the log.

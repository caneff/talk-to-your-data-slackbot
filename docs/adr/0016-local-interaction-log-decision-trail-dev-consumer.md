# Local Interaction Log as the Decision Trail's dev consumer

Status: Accepted

Every **Data Question** handled by the Slack Assistant Adapter will append one
structured JSON line to a gitignored, retention-bounded **Interaction Log** at
`logs/interactions.jsonl`. The record carries the question, the response, latency,
the model, and — for answers — the **Question Frame**, the routed Data Request,
the **Prepared Data** *shape* (rows × columns) plus quality notes, and the tiny
`key_data` headline numbers. The Interaction Log is the local-dev consumer the
roadmap's deferred **Decision Trail** was waiting for: a maintainer turns a
logged interaction into an improvement via Claude Code, driven by the
`triage-flagged-interactions` skill. Retention
preserves the most useful improvement evidence first while enforcing a hard
local file-size cap.

## Considered Options

- **Defer the Decision Trail entirely.** On the roadmap, but it was waiting for a
  concrete consumer. Rejected: the maintainer's "paste me an interaction and
  improve it" workflow is exactly that consumer, and waiting longer keeps the
  trail abstract.
- **Append-first, compacted JSONL (chosen).** One `json.dumps(record)` line per
  request, greppable and diffable, owned by a flat `interaction_log` module that
  holds all file I/O and the schema. Normal writes append one line. When the
  Interaction Log Retention Policy is violated, the module atomically rewrites
  the file to keep useful records while staying under the configured cap.
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
- The consumer side is operationalized by the `triage-flagged-interactions`
  skill (`.claude/skills/`). It reads `logs/interactions.jsonl`, keeps records
  with a non-empty `flags` list, root-causes each flag to a pipeline layer using
  the recorded debug signal (`question_frame`, routed request, `prepared_data_shape`,
  `quality_notes`, `key_data`, or `stage`/`reason_code`), and routes the fix —
  reproducing locally when the sanitized shape is insufficient rather than
  inventing the omitted cell values. It treats the log as read-only except for
  `clear_flags` on maintainer-confirmed handled ids.
- Capture lives at the **Slack Assistant Adapter** (`on_user_message`), which
  already holds the full result, latency, and user in scope. The pure pipeline
  runner stays I/O-free, so the demo, tests, and evals never write logs.
- A new optional `FinalResponse.non_answer` field (backward-compatible, default
  `None`, populated by `compose_non_answer_response`) lets non-answer records
  record the fine 15-way `reason_code` + `stage` instead of the coarse 4-bucket
  `ResponseKind`.
- A logging failure never breaks the user reply: the append is wrapped so the
  user-facing `say` always wins.
- The Interaction Log Retention Policy keeps records by usefulness first and
  age second. Flagged records, error records, malformed JSONL lines, and
  Non-Answer records outrank unflagged answer records; the newest 5,000
  unflagged answer records are kept when space allows. A 100 MiB hard cap still
  wins over every category, so old flagged, error, malformed, or Non-Answer
  records can be deleted if they alone exceed the cap. Retained lines stay in
  original chronological file order.
- Flags remain attributes on the Interaction Log record. There is no separate
  flagged-record archive, so retention policy and flag state have one source of
  truth. For retention, any non-empty `flags` list counts as flagged, even if
  the category vocabulary later changes.
- Retention is checked after appending an interaction and after flagging an
  interaction. The file is rewritten only when the log exceeds its 100 MiB
  trigger size. When compaction runs, it rewrites the log to 50 MiB or less so
  normal appends do not repeatedly rewrite a file hovering near the cap. The
  5,000 recent unflagged answer record limit is a compaction target, not an
  independent rewrite trigger.
- Size thresholds use ordinary file bytes: `path.stat().st_size` decides whether
  to compact, and retained UTF-8 JSONL line lengths plus newlines decide whether
  the compacted file fits the 50 MiB target. The target wins during compaction;
  if one retained line alone exceeds 50 MiB, that line may remain rather than
  writing an empty log.
- Retention applies to every Interaction Log path, including injected test
  paths. The policy is injectable so tests can use tiny byte and count limits
  without touching the canonical local log.
- If retention has already removed a record, later flag attempts for that
  interaction id return `False`; there is no archive lookup or recovery path.
- The Slack Assistant Adapter keeps the existing "reply wins" boundary:
  retention failures are logged and dropped with append failures. Direct
  `interaction_log` module calls still raise filesystem or rewrite errors so
  tests and maintenance tools can detect them.
- Reversing later means deleting the `interaction_log` module, the adapter
  capture, and the optional `FinalResponse.non_answer` field; nothing else
  depends on the log.

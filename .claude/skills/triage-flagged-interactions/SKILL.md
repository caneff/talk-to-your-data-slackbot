---
name: triage-flagged-interactions
description: Review flagged Data Assistant interactions from the local Interaction Log and turn them into fixes. Use when the user says "look at the flagged cases", "flagged correctness cases", "flagged formatting cases", "triage the flags", or asks why a logged Assistant response was bad.
---

# Triage Flagged Interactions

Turn maintainer flags on Data Assistant responses into root-caused, actionable work. Reads the local **Interaction Log** (see ADR-0016, CONTEXT.md: *Interaction Log*, *Flag*), groups the flagged cases, locates the failing pipeline layer, and proposes fixes — without ever inventing data the log does not contain.

## Source of truth

- Log file: `logs/interactions.jsonl` (gitignored, append-only, one JSON object per Data Question). Written by `interaction_log.append_interaction`; flagged in place by `interaction_log.flag_interaction`.
- Hosted Render Worker file: `/var/data/interactions.jsonl` when `DATA_ASSISTANT_INTERACTION_LOG_PATH=/var/data/interactions.jsonl` is configured from `render.yaml`.
- Hosted Render flags are mirrored into Render application logs with prefix `data_assistant.flagged_interaction ` followed by the full sanitized JSON record. Use Render log tooling to fetch these records when the user asks about the Render/hosted instance or the local log has no flags.
- A **flagged** record has a non-empty `flags` array. Categories (exact): `correctness`, `formatting`, `investigate` (= `interaction_log.FLAG_VOCABULARY`).
- If the file does not exist or has no flagged records, say so plainly and stop — do not fabricate cases.

## Record schema (what you may rely on)

Every record:
`id`, `timestamp`, `user`, `question`, `latency_ms`, `outcome` (`answer` | `non_answer` | `error`), `response_text`, `model`, `flags: [...]`.

Manual QA driver records may also include `qa_case_id`. Treat it as the stable
QA-case join key for Known QA Issue sidecars only when the record also has
`source == "qa_review"`. Keep `question` as observed evidence only; never use
question text as the sidecar key.

QA Review Mode records (`source == "qa_review"`) may also carry an optional
`qa_review_note`: the QA reviewer's free-text complaint, written via
`interaction_log.save_qa_review_note`. When present it is the **strongest human
signal** about what is wrong — it states what the reviewer actually observed, in
their own words. Treat it as primary evidence, not flavor text.

By `outcome`:
- **answer:** `intent`, `question_frame` (`intent`, `metric`, `time_scope`, `filters`, `unresolved_ambiguities`), routed `dataset` / `metric` / `metric_expression` / `group_by` / `filters` / `result_limit`, `prepared_data_shape` (`rows`×`columns`), `quality_notes`, and `key_data` (the tiny headline numbers).
- **non_answer:** `stage`, `reason_code` (the fine 15-way `NonAnswerReasonCode`), `context`.
- **error:** `error_type`, `error_message`.

### Sanitization boundary — do not pretend otherwise

The log deliberately **excludes raw Prepared Data cell values** (ADR-0016). You get prepared-data *shape* + `quality_notes` + the small `key_data` only. When a flag needs more than that to diagnose, **reproduce the question locally** against the dev data rather than guessing the missing rows.

## Process

### 1. Load the flagged set
Read `logs/interactions.jsonl`, parse each line, keep records with non-empty `flags`. If the user named a category (`correctness` / `formatting` / `investigate`), filter to it. Report the count and the category split.

For Render/hosted triage, query application logs for `data_assistant.flagged_interaction `, parse the JSON payload after that prefix, and treat those payloads as the flagged set. If multiple log entries exist for the same `id`, keep the newest payload because later clicks may add categories. Render log access is an observation path, not a write path: do not claim flags were cleared from the hosted file unless you actually ran `interaction_log.clear_flags` against `/var/data/interactions.jsonl` in the Worker.

### 2. Present each flagged case
For every flagged record show, compactly:
- `id`, `timestamp`, category(ies), `outcome`, `qa_case_id` when present, the
  `question`, and the `response_text`.
- The operator note (`qa_review_note`), verbatim, when present — call it out
  prominently so it is never silently dropped. It is the human's stated
  complaint and drives the root-cause below.
- The debug signal for its outcome:
  - answer → `intent`, routed `dataset`/`metric`(`metric_expression`)/`group_by`/`filters`, `time_scope`, `prepared_data_shape`, `quality_notes`, `key_data`, plus any `unresolved_ambiguities`.
  - non_answer → `stage` + `reason_code` + `context`.
  - error → `error_type` + `error_message`.

### 3. Root-cause to a layer

**When `qa_review_note` is present, it is the PRIMARY root-cause signal.** It is
the human's stated complaint, not a hint — diagnose the problem the note
describes. Signals you auto-infer from `response_text` (e.g. a stray lowercase
letter) must **not** replace or override the operator's stated complaint. If the
note conflicts with your inference, the note wins: reproduce locally (step 4) to
reconcile the two rather than discarding the note. Only when there is no
`qa_review_note` do you lead with the auto-inferred signals in the table below.

Map each case to the most likely failing stage, using the category as a strong hint:

| Signal | Likely layer | Code anchor |
|---|---|---|
| Wrong `intent` / `metric` / `time_scope` / bad `filters` in `question_frame`; `correctness` flag | **Question Interpreter** | `question_interpreter/` |
| Wrong/ambiguous `dataset` or table selection; `reason_code` like `no_matching_dataset` / `ambiguous_*` | **Semantic Router** | `semantic_router.py`, `semantic_matcher.py` |
| Denied when it should answer | **Access Controller** | `access_controller.py` |
| Numbers wrong but routing right; `key_data` mismatches the question | **Data retrieval / request** | `workflow/runner.py`, `DataRequest` |
| Prose wrong/misleading but numbers right; narrative drift | **Reasoning Layer** | `reasoning_layer/` (cf. ADR-0012) |
| `formatting` flag — bad blocks/table/trust summary, right content | **Response Composer** | `response_composer.py` |
| `investigate` flag — response is acceptable, but an internal signal warrants code analysis (`reason_code` e.g. `invalid_provider_output` / `provider_failure`, high `latency_ms`, suspicious `quality_notes`) | the layer that emitted the recorded internal signal | per-stage; **reproduce locally** to see the raw payload the log omits |
| `non_answer` that should have answered | stage named in `stage` field | per-stage |

`formatting` flags almost always live in the **Response Composer**; `correctness` flags live upstream (interpreter → router → retrieval → reasoning). Use `reason_code`/`stage` to skip straight to the stage on non-answers.

`investigate` flags are about the **system**, not the user-facing answer: the response was acceptable (e.g. an honest Non-Answer like "the Question Interpreter provider returned invalid output"), but the maintainer wants the internal behavior analyzed in code. Do **not** assume the response is wrong. Read the recorded internal signal (`reason_code`, `latency_ms`, `quality_notes`) and **reproduce locally** to see the raw payload the log omits (ADR-0016 sanitization), then route to a code investigation. The "flagged ≠ confirmed bug" caution applies doubly here — the flag is a hint to look, not evidence of a defect.

### 4. Reproduce when the log is insufficient
If shape + `key_data` cannot confirm the root cause, reproduce locally (the log omits cell values by design):
- Run the question through the dev pipeline / live-eval harness against the seeded retail data.
- Compare the produced `DataAssistantRun` trace to the logged record.
Never assert a cause that requires data the record does not carry.

### 5. Recommend action (read-only by default)
Default triage is read-only: present findings, root-cause mapping, and proposed issue/fix text. Do **not** create GitHub issues, comment on issues, clear flags, rewrite logs, or mutate any external system unless the user explicitly confirms that action in the current turn.

Group cases by root-caused layer (several flags often share one cause). For each group recommend the smallest fix and route it:
- Clear, bounded fix → propose `/handle-next-issue` (or a direct fix) naming the file/layer, and include draft issue/fix text if useful.
- Broader or fuzzy → propose `/to-issues` to slice it, and include draft issue text if useful.
- `investigate` flag → propose a **code investigation / engineering issue** (via `/to-issues` or a direct fix on the layer that emitted the signal), NOT a response-copy fix — the user-facing answer is fine; the system behavior is what needs analyzing.
- Already-tracked root cause → if a flag's root cause is already covered by an open issue, just map the `id` to that issue number and move on. Do **not** file a duplicate, do **not** comment on the existing issue, and do **not** propose "repeat occurrence" / "additional occurrence" notes. Repeat flags on a known cause are confirmation noise, not new signal; the mapping in your triage output is the only record needed.
Reference flags by `id` so the user can trace each back to its log line.

When a handled QA Review Mode flag has a confirmed mapping to a GitHub issue,
update the matching Known QA Issue sidecar only after that human judgment is
locked in:
- existing issue mapping confirmed → add `(qa_case_id, issue_number, flag_category)`
- new issue created for the flag → add same sidecar entry as part of handling
- sidecar-eligible means `record["source"] == "qa_review"` and
  `record["qa_case_id"]` is a present non-empty string
- do **not** add sidecar entries for raw flag clicks, unconfirmed flags,
  working-as-intended outcomes, normal Slack or hosted Render records without
  valid QA metadata, or records missing either gate above
- preflight remains create/validate/prune only; it must never infer new
  sidecar entries from flagged records

Record the confirmed mapping with the operator script
`scripts/record_known_issue.py` (a thin CLI over the
`record_known_issue_for_qa_record(...)` eligibility gate in
`data_assistant.known_qa_issues`). All three flags are required, so an unknown
or ineligible case id is a no-op (non-zero exit) rather than a bogus entry:
```bash
uv run python scripts/record_known_issue.py \
  --qa-case-id <qa-case-id> --issue-number <N> --flag-category correctness
```
Pass `--battery-path` to target a non-default battery.

When the user explicitly confirms filing an issue in the current turn, **apply the `priority:low` label to every issue you file from a flag** unless the user says a particular flag is urgent. Flagged-interaction issues are demand-driven noise that should NOT jump ahead of roadmap work; the label tells `handle-next-issue` not to favor them (it picks default-priority issues first). Create the label if absent, then file with it:
```bash
gh label create "priority:low" --color c5def5 \
  --description "Deprioritized: do not favor over default-priority work when picking the next issue" 2>/dev/null || true
gh issue create --label "priority:low" --label bug --title "..." --body "..."
```
If the user explicitly says a particular flag is urgent, omit the label for that one and say so.

### 6. Clear the handled flags (default)
Once you file the issue(s), map an `id` to an already-tracked issue, complete the fix(es), or determine no action is needed (working-as-intended), that flag is *handled* — it should drop out of the flagged set so the next triage starts clean. **Clear handled flags by default**:

- Clearing is the **default**. Do **not** ask first — clear every `id` you handled this session, then report exactly what you cleared.
- **The only exception is a preemptive opt-out.** If the user said earlier in this session not to clear flags (or not to clear a particular `id`), honor that and keep those flagged. A preemptive "don't clear" overrides the default; absent it, clear.
- List the exact `id`s you cleared and the issue / fix / WAI determination each maps to.
- If a handled flag also produced a Known QA Issue sidecar update, report that
  sidecar path and `(qa_case_id, issue_number, flag_category)` mapping
  alongside the cleared `id`.
- Clear handled `id`s with `scripts/clear_flags.py` — this **empties each record's `flags` list but keeps the interaction line** (still useful as an improvement corpus; it is not a delete). It takes any number of ids at once and prints a per-id result table:
  ```bash
  uv run python scripts/clear_flags.py <id> [<id> ...]
  ```
  Each line is `id<TAB>True/False`: `True` when a still-flagged record was found and emptied, `False` on an unknown id or an already-unflagged record. Pass `--log-path /var/data/interactions.jsonl` (via a worker) to clear the hosted log.
- Clear **only** the `id`s you actually handled this session. Leave untouched any flag you did not triage to a resolution. Never delete a record or rewrite anything other than the `flags` of handled ids.

## Guardrails
- Triage analysis is read-only, and **issue/external mutations** (create issues, comment on issues, rewrite logs, mutate external systems) still require the user's explicit confirmation in the current turn. **Clearing handled flags is the exception**: it is the default closeout (step 6) and needs no separate approval — unless the user preemptively opted out.
- The log is read-only during analysis. The **only** permitted log write is `clear_flags` on ids you handled this session (step 6) — done by default, skipped only on a preemptive user opt-out. Never delete a record, never rewrite anything but the `flags` of handled ids, never clear a flag you did not handle.
- Read the operator's `qa_review_note` first when present; it is the human's stated complaint, not a hint. Never override it with a root cause inferred from `response_text`.
- Never fabricate questions, numbers, or rows not present in the record. Cite `id`s.
- Respect the sanitization boundary — reproduce locally instead of inferring hidden cell values.
- Flagged ≠ confirmed bug. A flag is a maintainer's signal; verify the root cause before proposing a fix.
- Keep each proposed fix to one layer / one concern where possible (cf. git-workflow-and-versioning: separate concerns).
- Never comment on existing issues or suggest "repeat occurrence" notes for flags whose root cause is already tracked. Map the `id` to the open issue in your triage output and stop there.

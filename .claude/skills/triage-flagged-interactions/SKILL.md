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
- `id`, `timestamp`, category(ies), `outcome`, the `question`, and the `response_text`.
- The debug signal for its outcome:
  - answer → `intent`, routed `dataset`/`metric`(`metric_expression`)/`group_by`/`filters`, `time_scope`, `prepared_data_shape`, `quality_notes`, `key_data`, plus any `unresolved_ambiguities`.
  - non_answer → `stage` + `reason_code` + `context`.
  - error → `error_type` + `error_message`.

### 3. Root-cause to a layer
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

### 5. Propose action
Group cases by root-caused layer (several flags often share one cause). For each group recommend the smallest fix and route it:
- Clear, bounded fix → suggest `/handle-next-issue` (or a direct fix) naming the file/layer.
- Broader or fuzzy → suggest `/to-issues` to slice it.
- `investigate` flag → route to a **code investigation / engineering issue** (use `/to-issues` or a direct fix on the layer that emitted the signal), NOT a response-copy fix — the user-facing answer is fine; the system behavior is what needs analyzing.
- Already-tracked root cause → if a flag's root cause is already covered by an open issue, just map the `id` to that issue number and move on. Do **not** file a duplicate, do **not** comment on the existing issue, and do **not** propose "repeat occurrence" / "additional occurrence" notes. Repeat flags on a known cause are confirmation noise, not new signal; the mapping in your triage output is the only record needed.
Reference flags by `id` so the user can trace each back to its log line.

**Apply the `priority:low` label to every issue you file from a flag.** Flagged-interaction issues are demand-driven noise that should NOT jump ahead of roadmap work; the label tells `handle-next-issue` not to favor them (it picks default-priority issues first). Create the label if absent, then file with it:
```bash
gh label create "priority:low" --color c5def5 \
  --description "Deprioritized: do not favor over default-priority work when picking the next issue" 2>/dev/null || true
gh issue create --label "priority:low" --label bug --title "..." --body "..."
```
If the user explicitly says a particular flag is urgent, omit the label for that one and say so.

### 6. Offer to clear the handled flags (only on explicit confirmation)
After filing the issues / fixes, a flag is *handled* — it should drop out of the flagged set so the next triage starts clean. Offer to clear it:

- List the exact `id`s you handled this session and the issue/fix each maps to.
- **Ask** the user whether to clear those flags. Default to **not** clearing. Never clear without an explicit yes.
- On yes, clear each confirmed `id` with `interaction_log.clear_flags(id)` — this **empties the record's `flags` list but keeps the interaction line** (still useful as an improvement corpus; it is not a delete). Run it via the project env, e.g.:
  ```bash
  uv run python -c "from data_assistant import interaction_log; print(interaction_log.clear_flags('<id>'))"
  ```
  It returns `True` when a still-flagged record was found and emptied, `False` on an unknown id or an already-unflagged record.
- Clear **only** the `id`s you actually handled and the user confirmed. Leave every other flagged record untouched. Never delete a record or rewrite anything other than the `flags` of confirmed ids.

## Guardrails
- The log is read-only during analysis. The **only** permitted write is `clear_flags` on confirmed-handled ids, and **only** after the user explicitly approves it (step 6). Never delete a record, never rewrite anything but the `flags` of confirmed ids, never clear a flag you did not handle.
- Never fabricate questions, numbers, or rows not present in the record. Cite `id`s.
- Respect the sanitization boundary — reproduce locally instead of inferring hidden cell values.
- Flagged ≠ confirmed bug. A flag is a maintainer's signal; verify the root cause before proposing a fix.
- Keep each proposed fix to one layer / one concern where possible (cf. git-workflow-and-versioning: separate concerns).
- Never comment on existing issues or suggest "repeat occurrence" notes for flags whose root cause is already tracked. Map the `id` to the open issue in your triage output and stop there.

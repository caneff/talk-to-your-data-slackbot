---
name: triage-eval-failures
description: Review failing cases from a live-eval failures JSONL and turn them into fixes. Use when the user says "triage the eval failures", "look at the live eval failures", "why did these interpreter cases fail", or asks to act on an `eval_results/*.jsonl` failures snapshot.
---

# Triage Eval Failures

Turn a live-eval **failures snapshot** into root-caused, actionable work. Reads the
JSONL file the live eval streams while running, sorts each failed case into one of six
**dispositions**, clusters cases that share a root cause, and routes each to the smallest
fix — without ever fabricating a verdict the record cannot support, and without spending
on the paid provider unless you approve it first.

This is the eval-side companion to `triage-flagged-interactions` (which triages
maintainer flags on shipped Assistant responses). This skill triages *eval* failures:
cases where the OpenAI Question Interpreter proposal did not match the pinned expected.

## Source of truth

- Failures file: `eval_results/live_eval_failures_<UTC>.jsonl` (gitignored), streamed by
  the live eval one JSON object per failed case, flushed as each case finishes. Written by
  `question_interpreter/live_eval.py` (`_write_failure_line`). The file is
  **truncate-at-start, regenerated every run** — a disposable snapshot, not a durable
  store. A clean run leaves an **empty file** (proof the run completed and found nothing).
- **File selection.** With no path given, default to the **newest**
  `eval_results/live_eval_failures_*.jsonl` (glob, newest mtime). Honor an explicit path
  if the user names one.
- Coverage today is the **question_interpreter** eval only. Keep the disposition language
  eval-agnostic so a future `reasoning_layer` failures file in the same schema drops in
  unchanged. The `workflow` eval is single-question and emits no failures file — out of
  scope.
- If the file is missing or empty, **say so plainly and stop** — an empty file means the
  run was clean. Do not fabricate failures.

## Record schema (what you may rely on)

Every line (`_write_failure_line`, `live_eval.py`):

```json
{"case_number": 44, "case_name": "trend_order_count_by_order_date_q1",
 "question": "...", "pass_count": 0, "sample_count": 3,
 "reasons": ["sample 1: field_operations: expected ..., got ...", "..."],
 "expected": { ...QuestionFrameProposal.model_dump()... },
 "actual":   { ...proposal dump... }}
```

- `case_number` = the case's **absolute 1-based index in the enabled list**, always —
  the disambiguator, independent of which selection flag produced the run. Use it to
  re-run a case by index, and cite it in the summary.
- `pass_count` / `sample_count` = how many of the `k` provider samples matched expected.
- `reasons[]` = per-failing-sample mismatch strings (which field: `intent` / `metric` /
  `field_operations`).
- When the provider itself failed, `actual` is `{"provider_failure": "<reason>"}` instead
  of a proposal dump (`_failure_actual_payload`).

## Dispositions

Sort every failed case into exactly one:

| Disposition | Signal | Action |
|---|---|---|
| **flake** | `0 < pass_count < sample_count`; reasons differ across samples | **ambiguous — ask the user.** Do not auto-rerun |
| **provider-failure** | `actual = {"provider_failure": ...}` | infra/transient (rate-limit, invalid output) — re-run; if persistent, note an infra issue |
| **expected-wrong** | `pass_count = 0`; the provider's `actual` is the *defensible* answer, pinned `expected` is too strict/incorrect | fix the case in `question_frame_cases.py` (direct edit OK) |
| **prompt-weak** | `pass_count = 0`; provider consistently emits the *same wrong* shape, `expected` is right | fix interpreter prompt in `proposals.py` → `/handle-next-issue` |
| **known-limitation** | deferred intent / out-of-data-window the provider genuinely can't do yet | WAI; optionally mark the case known-deferred so it stops re-surfacing |
| **schema-drift** | an `expected` label (`metric` / op `field` / `intent`) no longer exists in the catalog; hits many cases identically | mechanical re-sync sweep + surface "a label rename skipped the eval cases" → `/handle-next-issue` |

Separations that matter:

- **expected-wrong vs prompt-weak** — both are `0/k` and well-formed. Split on *who is
  right*: provider defensible → expected-wrong; expected right → prompt-weak.
- **schema-drift short-circuits that judgment.** If a label is dead in the catalog, it is
  drift — deterministic, no defensibility call. Check drift first.
- **flake is not "just re-run."** A `2/3` flake's failing sample may carry the *same*
  mismatch as a real prompt-weak/expected-wrong. Surface the failing sample's `reasons`
  and pass ratio and **ask the user** how to handle it.

## Evidence ladder (free → consented-paid)

The only way to get fresh provider output is to run the **paid** live eval. Climb this
ladder; do not skip to a verdict you can't support.

1. **Free / deterministic first.** Read whatever you need at no cost:
   - `proposals.py` — the `FieldOperationProposal.operation` Literal and
     `QuestionFrameProposal` shape (what's a valid op / field).
   - Semantic-layer YAML at `examples/retail_ops_demo/semantic_layer/tables/*.yaml` — the
     live set of metric/field labels. Cross-check every `expected` label here; a dead
     label ⇒ **schema-drift**, decided.
   - `git log` / `git blame` on `question_frame_cases.py` and the YAML — a case that
     drifted from a recent rename shows up here.
   - The record's own `reasons[]` + `expected`/`actual` dumps — argue defensibility from
     these.
2. **Judgment from the record.** Decide expected-wrong vs prompt-weak from the dumps +
   schema knowledge. "Insufficient evidence to decide" is an **honest, valid outcome** —
   it ends in a proposed scoped re-run, never a fabricated verdict.
3. **Consented paid re-run (escalation only).** When free evidence can't decide — or to
   confirm a flake — you **may** run the live eval, but:
   - **Ask explicit permission in the current turn**, and **state the cost** first
     (`3 cases × 10 samples = 30 paid calls`).
   - **Scope tightly** with `--only-cases` to the cases under triage — never the full
     battery.
   - Never run it unprompted or by default.

## Re-run recipe (the live-eval CLI)

Module: `python -m data_assistant.question_interpreter.live_eval`. Relevant flags
(shipped in #175):

- `--only-cases <name|idx>` — run only these enabled cases, by `case_name` or 1-based
  `case_number`; comma-separated and/or repeatable. Scope every re-run with this.
- `--samples N` — provider samples per case; `--samples 10` to confirm a flake.
- `--failures-out PATH` — where the next snapshot lands (default: a fresh timestamped
  file under `eval_results/`).
- `--start-at` / `--stop-at` — 1-based slice of the enabled list (mutually exclusive with
  `--only-cases`).

Emit re-runs as a `!`-prefixed command the user runs (it's paid), e.g. confirm a flake on
two cases at higher sampling:

```
! uv run python -m data_assistant.question_interpreter.live_eval --only-cases exact_date_net_revenue,12 --samples 10
```

## Process

### 1. Load & summarize
Resolve the file (newest in `eval_results/` or the named path). Parse each line. If
missing/empty, say so and stop. Otherwise report the count and a one-line disposition
split, e.g. `2 flake, 1 provider-failure, 4 prompt-weak, 3 schema-drift, 1 known-limitation`.

### 2. Disposition (drift-first)
For each case, run the evidence ladder. Cross-check labels against the catalog **first**
(catches schema-drift cheaply), then read the pass ratio / `provider_failure` marker, then
judge expected-wrong vs prompt-weak. Where the record can't decide, mark it
"needs a scoped re-run" rather than guessing.

### 3. Group & order
Group by disposition, and **within** a disposition cluster cases that share one root cause
(all `total net revenue` drift cases together; all "collapsed group_by+range_filter"
prompt-weak cases together) so one fix maps to many `case_number`s. Present in
**leverage order**: schema-drift → prompt-weak → expected-wrong → flake → known-limitation
→ provider-failure.

### 4. Recommend action (read-only by default)
Default triage is **read-only**: present findings, root-cause, and proposed fix/issue/
re-run text. Per disposition:
- **schema-drift** → mechanical re-sync sweep across the stale cases; if more than one
  case or it touches shared shape, route via `/handle-next-issue`. Surface the process
  miss ("rename X→Y skipped the eval cases").
- **prompt-weak** → prompt fix in `proposals.py`; high blast radius (affects every case) →
  `/handle-next-issue`, with a full re-run after.
- **expected-wrong** → single bounded case fix → **direct edit allowed on confirm**;
  multi-case → `/handle-next-issue`.
- **flake** → present pass ratio + failing-sample `reasons`; **ask the user** (confirm by
  re-run, or treat as a real expected-wrong/prompt-weak and fix).
- **known-limitation** → WAI; offer to annotate the case as known-deferred so it stops
  re-surfacing. Don't "fix" a working-as-intended deferral.
- **provider-failure** → propose a scoped re-run; only if it persists across runs, an
  infra/provider issue.
- Do **not** auto-label filed issues `priority:low` — eval failures are real quality
  signal, not demand-driven noise. Let the user set urgency.

### 5. Closeout summary
End with an inline triage summary — one row per case: `case_number case_name →
disposition → action`. Collapse shared-root-cause clusters onto one action line. After any
fixes land, **recommend a full re-run** to regenerate the failures file (empty file =
confirmed clean) — state the cost and get permission per the evidence ladder. Do not
persist a summary file unless asked.

## Guardrails

- **Never run the paid live eval unprompted.** Running it requires explicit permission in
  the current turn, a stated call count, and `--only-cases` scoping. Free reads
  (code, YAML, catalog, git, the failures file) need no approval.
- **Read-only analysis by default.** File edits, issue creation, and `git` mutations need
  the user's explicit confirmation in the current turn — except a single bounded
  expected-wrong case edit, which is allowed on confirm.
- **No clear-handled step.** The failures file is disposable (truncate-at-start) — there
  is no flag to clear. The durable output is the fixes/issues; re-running regenerates the
  snapshot.
- **Never fabricate a verdict.** "Insufficient evidence" ends in a proposed scoped re-run,
  not a guess. Cite `case_number` for everything.
- **Schema-drift is detection, not judgment** — confirm the dead label against the live
  catalog before calling it; don't infer a rename from vibes.
- **Failed ≠ wrong expected.** A failing case is a signal; decide *which* side is wrong
  (expected vs prompt) before proposing a fix.
- Keep each fix to one layer / one concern (cf. git-workflow-and-versioning): cases file
  for expected-wrong/drift, `proposals.py` for prompt-weak — not both in one change.

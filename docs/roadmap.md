# Product Roadmap

This roadmap keeps the first implementation small while preserving the larger
Data Assistant ideas for later expansion.

## Final-Project Demo Push (4-day, prioritized)

Target: a 5-minute live Slack DM demo. Differentiator: the assistant refuses to
fabricate — grounded answers, visible degradation, and **Non-Answer Responses**
instead of confident guesses. Favor code quality over scope; never put an
unfinished feature on the demo path.

Work in strict value order. Each item must be green (tests, pyright, ruff) and
rehearsed before the next starts. Tracked as issues #99 (resilience), #100
(Assistant surface), #101 (retail demo target), #102 (top-N + table), #103
(stretch: clarification turn).

1. **Resilience** (must, cheap — protects the live demo). Set an explicit
   request timeout (~15s) and an explicit `max_retries` (1) on both OpenAI
   providers; the SDK already retries transient errors and the only real
   demo-killer is the 600s default read timeout. A bounded call falls through to
   the existing typed **Non-Answer** instead of a silent on-stage hang. ~2h.
2. **Convert to a Slack Assistant** (the demo surface; diverges from the course's
   classic-bot manifest — see ADR-0015). ~1–1.5 days; touches the working path,
   so do it while fresh and re-rehearse after.
   - **Manifest**: add `features.assistant_view` (`assistant_description`,
     optional static `suggested_prompts: [{title, message}]`); scopes
     `assistant:write` + `chat:write` + `im:history`; events
     `assistant_thread_started`, `assistant_thread_context_changed`, `message.im`.
     Reinstall the app.
   - **Code**: a dedicated `AssistantAdapter` on Bolt's `Assistant` container —
     NOT routed through the old `handle_slack_event` / `SlackGateway` envelope.
     Reuse only the pipeline (`answer_path`) and lift `_render_workflow_result`.
     The adapter speaks the assistant model directly: `thread_started` → greeting
     + `set_suggested_prompts([retail Qs])`; `user_message` →
     `set_status("analyzing your data…")` → run pipeline → `say(reply)` (posting
     the reply auto-clears the status, so there is no separate "working" message).
   - The interpret→…→compose pipeline, evals, and Non-Answer path stay untouched;
     divergence is contained to the Slack edge.
3. **Retail dataset as the demo target.** Drive the existing `retail_ops` demo
   Semantic Layer (denormalized tables, no joins needed) via the runtime flags;
   rehearse and lock the demo questions (these feed the suggested prompts). Watch
   for routing ambiguity across the seven tables (e.g. "revenue" matching two
   tables) — phrase around it or use it as the refusal beat.
4. **Top-N intent + compact output.** Add a typed top-N **Supported Intent**
   (ORDER BY / LIMIT in deterministic retrieval per ADR-0014) and render the
   ranked result as a Slack table. Headline stays grounded
   (`led by {top_dimension} at {top_value}`); the table carries the ranking, so
   the existing Narrative Slots need no rework. Pressured by the Assistant cost.
5. **Stretch — agentic clarification turn.** Replace the refusal beat with an LLM
   follow-up question that resolves a **Material Ambiguity**, then proceeds. The
   Assistant container is natural groundwork for this; per ADR-0004 it is also
   the trigger to choose an orchestration framework. **Cut line.**

Honest budget: the Assistant conversion reclasses former "Chunk 1 insurance"
into a feature. Realistic 4-day outcome is resilience + Assistant + retail +
*one* of {top-N, clarification}, not both. The day-3 freeze governs.

**Day-3 freeze:** whatever is green-and-rehearsed is the demo. Anything
unfinished is reverted off the demo path, not dragged on stage half-built. The
refusal beat (built today) is the rehearsed default for Beat 2; the clarification
turn replaces it only if it lands green by the freeze.

Deliberately **not** in this push (talking points, not builds): multiple group-by
dimensions, multi-table joins (the demo data is denormalized precisely to avoid
them, and a join is invisible on stage), LLM text-to-SQL retrieval (ADR-0014),
observability / Decision Trail (invisible in a live demo), chart images.

## MVP

The MVP proves a thin, governed path from one Slack message containing one Data
Question to a Final Response grounded in one approved Curated Dataset.

### In Scope

- Receive a Data Question in Slack.
- Send a quick Slack Acknowledgement.
- Interpret the Data Question into a simple Question Frame.
- Select one Curated Dataset from the Semantic Layer.
- Check Dataset Access before data retrieval.
- Build a constrained Data Request.
- Produce bounded Prepared Data.
- Generate a concise Final Response.
- Include a Trust Summary with the Final Response.
- Return a Non-Answer Response when the assistant cannot safely answer.
- Store Semantic Layer definitions as versioned repo config.

### Not Yet

- Questions whose shape exceeds a single metric grouped by a single dimension:
  multiple group-by dimensions and multiple metrics per question are not yet
  supported (`data_preparation` uses `group_by_fields[0]`).
- Intents beyond `summarize` — trends, comparisons, top-N, and period-over-period
  are deliberately out of scope (`_SUPPORTED_PROVIDER_INTENTS` is `summarize`
  only).
- Multi-dataset joins.
- Result Access beyond simple dataset-level denial.
- Trust Detail follow-ups.
- Chart images.
- Repeated Clarification Loops.
- More Data Requests from the Reasoning Layer.
- Routing Cache.
- Prepared Data or Final Response caching.
- Interactive dashboards.
- Forecasting, prescriptive recommendations, automated root-cause analysis, or
  background anomaly detection.

## Future Expansion

### High Priority Follow-Ups

- The LLM-backed Question Interpreter slice is complete: #31 contract and eval
  harness, #34 OpenAI provider, and #33 manual live LLM eval suite are all
  delivered. ADR-0004 records the decision to use direct OpenAI SDK integration
  for the first live provider and defer LangChain/LangGraph until a second
  LLM-backed component or stateful conversation flow makes that trade-off
  concrete.
- Introduce an LLM-backed Question Interpreter in contract-first slices: first
  add the Question Frame proposal, validation, fake provider, and eval harness;
  then add the live LLM provider; then add a manual live LLM eval suite that can
  be run with one explicit command outside normal checks. The deterministic MVP
  interpreter was only application plumbing and should not be used as a
  real-application fallback.
- Treat interpretation, reasoning, response composition, and conversation flow
  as candidates for LLM-backed components. Keep access control, validation,
  Provider Proposal Validation, Semantic Layer loading, and data retrieval
  deterministic.
- Add Semantic Layer aliases for metrics and dimensions after the first
  LLM-backed interpreter slice, so common business phrasing can be safely
  promoted to canonical Question Frame values.
- Add Visual Payload support for compact Slack-friendly tables and simple chart
  images after LLM-backed interpretation and evals are in place.

### Code Quality Improvements

- Consolidate Semantic Layer matching so the Semantic Router and Data Requester
  share one canonical match result for Curated Dataset, Dataset Table, metric,
  and dimension instead of repeating label scans across stages, while Dataset
  Selection keeps dataset-level rationale.
- Add load-time Semantic Layer integrity validation and indexed lookups for
  unique dataset IDs, unique table IDs, Curated Dataset table references, and
  Dataset Table ownership.
- Tighten the Data Preparation retrieval boundary so Data Requests carry a
  prevalidated retrieval plan. Before expanding beyond the local demo, validate
  or quote SQL identifiers and replace raw metric SQL expressions with typed or
  whitelisted operations.
- Decompose Question Interpreter responsibilities before filters, intents, or
  providers grow: keep the OpenAI provider adapter, business-facing Semantic
  Layer context builder, and Question Frame Provider Proposal Validation in
  focused modules.
- Move Non-Answer Response rendering away from exact reason-string and
  ambiguity-tuple checks. Prefer a reason-code policy map or an explicit
  response-kind contract.
- Simplify Slack Runtime startup so live handler registration requires the
  needed answer path and connection factory explicitly, avoiding nullable mode
  branches that can start a runtime with no message handler.

### Better Conversation Flow

- Add bounded Clarification Loops for Material Ambiguity.
- Support Trust Detail Requests such as "show details" or "what data did you
  use?"
- Add stage-based Progress Updates for long-running analysis.

### Richer Data Access

- Support approved joins across multiple Curated Datasets.
- Add Result Access checks for sensitive fields, segments, and aggregation
  levels.
- Consider access-aware Dataset Selection so "several datasets match but the
  caller can access only one" resolves to an answer instead of an ambiguity
  Non-Answer. Per ADR-0006 this is a deliberate redefinition of whether the
  Semantic Router owns authorization, not a tiebreaker; it needs its own ADR and
  must preserve the exists-but-forbidden (`ACCESS_DENIED`) distinction.
- Let the Reasoning Layer emit More Data Requests that return through the
  Workflow Orchestrator.
- Reintroduce **data freshness / staleness** as a computed governance signal:
  compare each **Curated Dataset**'s as-of boundary against the question's time
  scope and the current date, warn or refuse when the requested window extends
  past the data and the answer would otherwise be a silent partial total,
  surface the data age in the **Trust Summary**, and require a freshness check
  before any **Routing Cache** reuse. The bootcamp demo stripped the earlier
  inert version — a static description string with an unread as-of date that no
  stage acted on — to keep the trust path simple; the real version is the
  window-past-freshness warning closed-as-deferred from issue #118.

### Richer Responses

- Add compact Slack-friendly tables where useful.
- Add simple chart images for trends and comparisons.
- Improve Non-Answer Responses with safer next-step guidance.

### Operational Hardening

- Revisit Decision Trail only when there is a concrete Trust Detail, demo,
  debug, or audit consumer. Keep interpreter correctness tests output-based, and
  any future Decision Trail artifact should record sanitized terminal outcomes
  rather than internal proposal/validation step ordering.
- Add Decision Trail metadata, counts, statuses, errors, and latency when that
  consumer exists, while excluding raw prompts, raw provider payloads, raw
  Prepared Data, secrets, SQL, chain-of-thought, and sensitive values.
- Add configurable Response Timing Defaults.
- Cache Semantic Layer metadata.
- Consider a Routing Cache if repeated specific Question Frames become common.

### Advanced Capabilities

- Forecasting.
- Prescriptive recommendations.
- Automated root-cause analysis across many datasets.
- Background anomaly detection.
- Interactive dashboards.

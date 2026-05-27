# Product Roadmap

This roadmap keeps the first implementation small while preserving the larger
Data Assistant ideas for later expansion.

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

- Current LLM-backed Question Interpreter sequence:
  #31 contract and eval harness; #34 OpenAI provider; #33 manual live LLM eval
  suite. ADR-0004 records the decision to use
  direct OpenAI SDK integration for the first live provider and defer
  LangChain/LangGraph until a second LLM-backed component or stateful
  conversation flow makes that trade-off concrete.
- Introduce an LLM-backed Question Interpreter in contract-first slices: first
  add the Question Frame proposal, validation, fake provider, and eval harness;
  then add the live LLM provider; then add a manual live LLM eval suite that can
  be run with one explicit command outside normal checks. The deterministic MVP
  interpreter was only application plumbing and should not be used as a
  real-application fallback.
- Treat interpretation, reasoning, response composition, and conversation flow
  as candidates for LLM-backed components. Keep access control, validation,
  promotion, Semantic Layer loading, and data retrieval deterministic.
- Add Semantic Layer aliases for metrics and dimensions after the first
  LLM-backed interpreter slice, so common business phrasing can be safely
  promoted to canonical Question Frame values.
- Add Visual Payload support for compact Slack-friendly tables and simple chart
  images after LLM-backed interpretation and evals are in place.

### Better Conversation Flow

- Add bounded Clarification Loops for Material Ambiguity.
- Support Trust Detail Requests such as "show details" or "what data did you
  use?"
- Add stage-based Progress Updates for long-running analysis.

### Richer Data Access

- Support approved joins across multiple Curated Datasets.
- Add Result Access checks for sensitive fields, segments, and aggregation
  levels.
- Let the Reasoning Layer emit More Data Requests that return through the
  Workflow Orchestrator.

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

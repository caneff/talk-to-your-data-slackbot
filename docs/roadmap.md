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

- Replace the deterministic MVP Question Interpreter with an LLM-backed
  interpreter once the Question Frame contract is stable.
- Add Visual Payload support for compact Slack-friendly tables and simple chart
  images once the plain-text Final Response contract is stable.

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

- Add a Decision Trail with decision metadata, counts, statuses, errors, and
  latency, while excluding raw Prepared Data and sensitive values.
- Add configurable Response Timing Defaults.
- Cache Semantic Layer metadata.
- Consider a Routing Cache if repeated specific Question Frames become common.

### Advanced Capabilities

- Forecasting.
- Prescriptive recommendations.
- Automated root-cause analysis across many datasets.
- Background anomaly detection.
- Interactive dashboards.

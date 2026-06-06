# Talk to Your Data Slackbot

Python project scaffold for a Slackbot that helps users talk to their data.

## What this version does differently

The common approach to "talk to your data" hands the question to an LLM, lets it
write the SQL, and lets it write the answer around whatever numbers come back —
quick to demo, but the model owns both the query and the prose, so a
wrong-but-plausible query reads like a confident answer. This version takes the
opposite stance: the LLM interprets and narrates, but never touches the bytes in
between. The decisions most worth calling out:

- **No text-to-SQL — retrieval is fully deterministic.** The LLM emits a typed
  `Question Frame` (intent, metric, dimension, filters, time range), and a plain
  `Data Requester` builds and runs the query, bounded by the `Semantic Layer`'s
  approved metrics and dimensions. Supporting a new question shape means adding a
  typed intent, not widening what the model may query. See
  [ADR-0014](docs/adr/0014-data-retrieval-stays-deterministic-no-text-to-sql.md).

- **The model never writes a number.** The `Reasoning Layer` writes prose around
  a fixed set of seven `Narrative Slots` (`{metric}`, `{metric_total}`,
  `{top_dimension}`, …) and the pipeline fills every slot from `Prepared Data`,
  formatted by `Metric Kind`. The model only ever sees a *figure-free*
  `Result Shape` — the slot names, never the values — and a zero-digit rule
  rejects any stray digit it emits. If it trips the rule or the provider fails,
  the answer degrades *visibly* to a deterministic template rather than inventing
  a figure. See
  [ADR-0012](docs/adr/0012-reasoning-layer-narrates-prose-pipeline-owns-numbers.md).

- **It returns a Non-Answer instead of guessing.** A question with no time period
  is treated as a `Material Ambiguity` — the bot asks you to narrow it rather than
  silently defaulting to all-time. v1 supports the summarize, rank, and
  catalog-discovery intents; an `Unsupported Intent Guard` cleanly rejects
  compare, trend, forecast, and explain questions instead of collapsing them
  into a grouped answer.

- **Meaning lives in versioned YAML, not a prompt.** The `Semantic Layer`
  (`examples/retail_ops_demo/semantic_layer/`) is the checked-in source of what the bot knows — datasets,
  metrics, dimensions, joins, access — so meaning is reviewable in git instead of
  hiding inside raw table names the model happened to read.

- **It runs on Slack's Assistant surface, not a plain DM bot.** The runtime uses
  Bolt's `Assistant` container, so answers arrive in a dedicated assistant pane
  with native transient status and suggested prompts — a deliberate divergence
  from the classic-bot manifest the course provides. See
  [ADR-0015](docs/adr/0015-adopt-slack-assistant-surface.md).

- **Bad answers are one click from becoming fixes.** Every answer carries
  *Flag correctness* / *Flag formatting* buttons. A flag appends to a local,
  retention-bounded `Interaction Log` (`logs/interactions.jsonl`) that records the
  `Question Frame`, routed request, result shape, and headline figures. The
  `triage-flagged-interactions` skill then reads those flagged records,
  root-causes each to a pipeline layer, and routes the fix. See
  [ADR-0016](docs/adr/0016-local-interaction-log-decision-trail-dev-consumer.md).

- **One image, no public URL.** Socket Mode dials an outbound WebSocket to Slack
  and binds no inbound port, so the `Dockerfile` image is the load-bearing
  artifact: `docker run` it locally with three secrets — no port config, no
  ngrok, no web server. The same image deploys unchanged to a Render
  **Background Worker** (via the `render.yaml` Blueprint) when a time-boxed
  hosted demo is wanted. See
  [ADR-0013](docs/adr/0013-demo-runs-via-local-docker-not-render.md).

- **Every answer carries a `Trust Summary`,** and access is checked *before* any
  data is pulled, so the bot can explain a denial without leaking what it denied.

The capitalized terms are the project's shared vocabulary, defined in
[CONTEXT.md](CONTEXT.md); the reasoning behind each decision lives in
[docs/adr/](docs/adr/).

## Slack MVP scope

This repo's Slack Runtime Adapter is DM-only.

Out of scope for this MVP:

- Channel mentions
- Slash commands
- Progress Updates
- Trust Detail follow-ups
- Public HTTP deployment

## Quickstart

Get the bot answering in your own Slack workspace:

1. Create the Slack app and set the local tokens — see
   [Local Slack setup](docs/operations.md#local-slack-setup).
2. Start the adapter:

   ```bash
   uv run python -m data_assistant.slack.runtime_main
   ```

3. DM the app a data question, e.g.
   `What was total net revenue by store region in Q1 2026?`

Full setup, Docker, and hosting live in
[Running the Slackbot](docs/operations.md).

## Running & evaluating

- [Running the Slackbot](docs/operations.md) — local Slack setup, starting the
  adapter, running in Docker, and hosting on Render.
- [Evaluating the Slackbot](docs/evaluation.md) — the manual acceptance check,
  the live Provider Proposal and Reasoning Layer evals, and the Slack QA driver.

## Development

Run checks with `uv`:

```bash
uv run pytest -q
uv run ruff check .
uv run pyright
```

Normal validation does not contact OpenAI.

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
  silently defaulting to all-time. v1 supports only the summarize intent; an
  `Unsupported Intent Guard` cleanly rejects rank/compare/trend questions instead
  of collapsing them into a grouped answer.

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

## Local Slack setup

This setup creates a private Slack app in your development workspace and runs
this repo as the app's local process. Socket Mode means the local process opens a
WebSocket connection out to Slack, so you do not need a public HTTP URL, ngrok,
or deployed web server for the MVP.

Create the Slack app from the repo manifest:

1. Open the Slack app dashboard: <https://api.slack.com/apps>.
2. Click **Create New App**.
3. Choose **From an app manifest**.
4. Pick your development workspace.
5. Copy the contents of `slack-app-manifest.yaml` into the YAML editor.
6. Review Slack's summary and click **Create**.

The manifest sets the MVP app shape for you:

- Socket Mode is enabled.
- The App Home Messages tab is enabled so users can DM the app.
- The bot can send DM replies with `chat:write`.
- The bot receives direct-message events with `im:history` and `message.im`.

Create a local `.env` file:

```bash
cp .env.example .env
```

You still need to create and copy the two local tokens into `.env`:

1. In **Basic Information**, create an app-level token with the
   `connections:write` scope. Replace `xapp-your-app-token` in `.env` with that
   token.
2. In **Install App**, install the app to the workspace.
3. In **OAuth & Permissions**, copy the bot user OAuth token. Replace
   `xoxb-your-bot-token` in `.env` with that token.

For the live OpenAI Question Interpreter, also set:

- `OPENAI_API_KEY`
- optional `OPENAI_MODEL`
  default is `gpt-4o-mini`

The runtime loads `.env` automatically with `python-dotenv`. Explicitly exported
environment variables still take precedence over values in `.env`. The `.env`
file is local only, and `.gitignore` keeps it out of commits. Do not commit token
values, workspace IDs, or other secrets.

Slack references:

- [Using Socket Mode](https://docs.slack.dev/apis/events-api/using-socket-mode/)
- [Bolt for Python Socket Mode](https://docs.slack.dev/tools/bolt-python/concepts/socket-mode/)
- [`message.im` event](https://docs.slack.dev/reference/events/message.im/)
- [`connections:write` scope](https://docs.slack.dev/reference/scopes/connections.write/)
- [`chat.postMessage` method](https://docs.slack.dev/reference/methods/chat.postMessage/)

## Start the adapter

Install dependencies and start the adapter:

```bash
uv run python -m data_assistant.slack.runtime_main
```

Startup requires `OPENAI_API_KEY`. Invalid structured output is retried once by
the Question Interpreter provider before falling through to the existing typed
Non-Answer path. Live provider failures and refusals also use that Non-Answer
path; the runtime does not fall back to a deterministic interpreter.

For local development, the runtime uses a tiny in-memory DuckDB `orders` table.
It is only there to support a manual Slack smoke test. No DuckDB database file
is committed.

To run the same Slack bot against a different Semantic Layer and DuckDB
location, pass runtime data flags:

```bash
uv run python -m data_assistant.slack.runtime_main --semantic-layer-path examples/retail_ops_demo/semantic_layer --duckdb-path :memory: --seed-sql-path examples/retail_ops_demo/seeds/retail_ops_seed.sql
```

`--seed-sql-path` is optional for an existing DuckDB file. It is useful for demo
data because startup stays one command.

## Run in Docker

Build local image:

```bash
docker build -t talk-to-your-data-slackbot:local .
```

Create local `.env` first:

- `SLACK_BOT_TOKEN`
- `SLACK_APP_TOKEN`
- `OPENAI_API_KEY`
- optional `OPENAI_MODEL`
  default is `gpt-4o-mini`

Run local Socket Mode adapter from the image:

```bash
docker run --env-file .env talk-to-your-data-slackbot:local
```

The Docker image starts the Retail Operations demo by default, using the
standalone Semantic Layer and deterministic DuckDB seed under
`examples/retail_ops_demo/`. The container still runs
`python -m data_assistant.slack.runtime_main`, so the Slack app from
`slack-app-manifest.yaml` is still required. Socket Mode opens an outbound
connection to Slack and binds no inbound port, so no `-p` flag is needed for
local Docker runs.

Override the command only if you want the tiny local smoke-test fixture instead:

```bash
docker run --env-file .env talk-to-your-data-slackbot:local python -m data_assistant.slack.runtime_main
```

## Host on Render (time-boxed demo)

For a short, time-boxed demo (~1 month) where the bot should answer without a
laptop running, deploy the same Docker image as a Render **Background Worker**.
This builds on the image from "Run in Docker" above — no rebuild or app change.

Use the `render.yaml` Blueprint at the repo root: in Render, create a new
Blueprint from this repo and it provisions a Background Worker built from
`Dockerfile`. A Background Worker has no inbound port and never spins down,
which matches Socket Mode (the adapter dials an outbound WebSocket to Slack and
binds no port — so the Worker needs no port config). The free tier does not
support Background Workers, so the Blueprint pins the lowest paid `starter` plan.

In the Render dashboard, set the secrets (declared `sync: false`, never
committed):

- `SLACK_BOT_TOKEN`
- `SLACK_APP_TOKEN`
- `OPENAI_API_KEY`
- optional `OPENAI_MODEL`
  default is `gpt-4o-mini`

The hosted Worker starts the Retail Operations demo by default, the same as the
local image, and still requires the Slack app from `slack-app-manifest.yaml`.

Render writes the Interaction Log to the attached persistent disk at
`/var/data/interactions.jsonl` via `DATA_ASSISTANT_INTERACTION_LOG_PATH`. When a
maintainer clicks a flag button, the Worker also mirrors that flagged,
sanitized record to application logs with the prefix
`data_assistant.flagged_interaction `. This keeps the full local JSONL durable
across deploys and lets Codex fetch flagged Render cases through Render logs for
triage.

**Cost warning:** the `starter` plan bills for the whole time the Worker runs,
and live OpenAI API cost is incurred per Data Question anyone asks while the
hosted demo is up.

**End-of-demo shutdown:** when the demo window is over, suspend or delete the
Render Worker (or delete the Blueprint) so the paid Worker stops billing. The
standing-charge tradeoff is only accepted for the boxed demo window; see
`docs/adr/0013-demo-runs-via-local-docker-not-render.md`.

## Manual Slack smoke test

A no-flag app run loads the **Retail Operations** layer
(`examples/retail_ops_demo/semantic_layer`) and seeds the retail demo data into
an in-memory DuckDB. (The library/test default stays on the Commerce example;
the retail default is an app-run concern only — see ADR-0001.)

1. Start the adapter with `uv run python -m data_assistant.slack.runtime_main`.
2. Open a DM with the app in Slack.
3. Send a supported question. The retail demo data answers net revenue by store
   region, so use:
   `What was total net revenue by store region in Q1 2026?`
4. Verify the bot replies in the same thread as the original message timestamp.
5. Verify the reply is a Final Response with a Trust Summary.
6. Verify the reply answers from the retail demo data, broken down by the four
   store regions (Northeast, Southeast, Midwest, West) with money figures.
7. Send the safe Non-Answer question:
   `What was total net revenue?`
8. Verify the bot replies with a Non-Answer Response that asks for the missing
   time scope and includes a Trust Summary.

## Manual live Provider Proposal Eval

Agent guard: do not run this or any other command that uses a real
`OPENAI_API_KEY` during normal development, validation, PR checks, or broad test
requests. Live OpenAI-backed commands cost API money and should run only when
the developer explicitly asks for that live run.

Run the live Provider Proposal Eval with `OPENAI_API_KEY` in `.env`:

```bash
uv run python -m data_assistant.question_interpreter.live_provider_proposal_eval
```

Use verbose output to print expected and actual proposal details for passed
cases too:

```bash
uv run python -m data_assistant.question_interpreter.live_provider_proposal_eval --verbose
```

Multi-case live evals show a `tqdm` case progress bar on stderr by default. Use
`--no-progress` when capturing logs:

```bash
uv run python -m data_assistant.question_interpreter.live_provider_proposal_eval --no-progress
```

Use bounded case concurrency to speed up live runs when current OpenAI limits allow
it. Samples within a case still run serially:

```bash
uv run python -m data_assistant.question_interpreter.live_provider_proposal_eval --concurrency 4
```

Optional model override in `.env`:

```dotenv
OPENAI_MODEL=gpt-4o-mini
```

The suite sends real OpenAI requests for a small set of enabled passing cases
and compares raw `propose_question_frame(...)` Provider Proposals against exact
expected proposals:

- `intent`
- `metric`
- `metric_ambiguity`
- `all_time`
- `field_operations`

Expected output shape:

```text
Total cases: 3
Passed: 3
Failed: 0
```

If any case fails, output includes each failed case name, question, expected
proposal, actual provider result, and field-level mismatch reason. Missing
`OPENAI_API_KEY` exits nonzero with a clear config error.

## Manual live Reasoning Layer evals

The same agent guard applies: do not run these without an explicit request for a
live OpenAI-backed run. Both read `OPENAI_API_KEY` (and optional `OPENAI_MODEL`)
from `.env`, and exit nonzero on any failure or missing key.

Run the Reasoning Layer narrative eval (grounding-property comparator, not exact
match) with `OPENAI_API_KEY` in `.env`:

```bash
uv run python -m data_assistant.reasoning_layer.live_eval
```

Use `--no-progress` to disable the stderr case progress bar when capturing logs.

It samples each enabled case k=3, passes only when every sample passes, reports
a per-case pass rate, and exits nonzero on any failure. The comparator asserts
grounding properties on `propose_narrative(...)` rather than prose exact-match:

- the required slot tokens appear in the raw proposal (e.g. `{top_dimension}`)
- the prose is grounded (no digit anywhere — slots carry every figure)
- the proposal fills (no unknown slot or stray brace)
- the pipeline's computed values land in the filled summary

The grounded cases need a gpt-4o-class model. The default `gpt-4o-mini`
under-performs the zero-digit rule because `result_shape` currently hands the
model digit-bearing values (the date range, the dimension count) it is asked not
to echo; set `OPENAI_MODEL=gpt-4o` for a representative run. The
`scalar_customer_count` case is disabled pending the value-free `result_shape`
fix tracked in issue #92.

Run the full-pipeline adversarial eval, which drives one adversarial question
end to end through every LLM layer (Question Interpreter and Reasoning Layer)
against a seeded in-memory DuckDB:

```bash
uv run python -m data_assistant.workflow.live_eval
```

It asserts the safe property — the final answer ships no fabricated figure: it
either grounds and fills with only legitimate pipeline values, or degrades
visibly to the deterministic template. It never asserts the live model always
degrades.

## Manual Slack QA driver

A maintainer tool that replays the curated QA battery
(`docs/qa-retail-questions.md`) through the **real** Slack Assistant answer
path one question at a time, posting each Final Response **as the bot** into an
assistant thread so you read it and press the existing flag buttons. Flags land
in the shared Interaction Log and feed the `triage-flagged-interactions` skill.
It is the recurring generator that refills the triage pipeline with observed
failures. See `src/data_assistant/slack_qa/driver.py` and **ADR-0016**.

The same agent guard applies: it runs the live OpenAI answer path and costs API
money, so run it only when you explicitly want a live QA pass — never during
normal development, validation, or PR checks.

Step by step:

1. Put `SLACK_BOT_TOKEN` and `OPENAI_API_KEY` (and optional `OPENAI_MODEL`) in
   `.env`.
2. **Start the LOCAL bot and leave it running, in the same working directory
   you will run the driver from:**

   ```bash
   uv run python -m data_assistant.slack.runtime_main
   ```

   The driver posts the answers, but the running bot owns the flag-button
   (`block_actions`) listeners and must share the same `logs/interactions.jsonl`
   file — so a flag you click attaches to the record the driver wrote.

   > **Note:** point the driver at your **local dev bot**, not the production
   > Slack app your team uses for real data questions. This drives the dev/test
   > instance: the driver uses `dev_identity` and the local dev data fixture (the
   > same dev config `slack_runtime` uses for the smoke test), so it answers from
   > local development data under a dev identity — not real curated datasets.
   > It must also be the **local** `slack_runtime`, not the live Render
   > deployment, because the driver and bot communicate only through local files:
   > the driver appends the interaction record to `logs/interactions.jsonl` and
   > reads the auto-discovery pointer `logs/last_assistant_thread.json`, while the
   > bot matches your flag click to a record by id in that same log. If the bot
   > runs on Render, your click hits Render's log (no matching record →
   > `flag_interaction` no-ops) and the pointer lives on Render's disk (so
   > auto-discovery can't read it). The Interaction Log is deliberately local
   > (**ADR-0016**), so: local dev bot, same directory.
3. In Slack, open the app under **Agents & AI Apps** and start a thread (the bot
   greets and shows suggested prompts). Opening the thread is enough — the bot
   records that thread as the driver's target (auto-discovery,
   last-writer-wins: the most recently opened thread).
4. Run the driver (defaults the battery to `docs/qa-retail-questions.md`, and
   posts into the thread you just opened — no ids needed):

   ```bash
   uv run python -m data_assistant.slack_qa.driver
   ```

   `--channel <CHANNEL>` and `--thread-ts <THREAD_TS>` remain as explicit
   overrides if you want to target a specific thread instead of the most
   recently opened one (each fills independently from the pointer when omitted).
   To get those ids manually: **Copy link** on a message in the thread — the link
   looks like `…/archives/<CHANNEL>/p1748880000123456`, where `<CHANNEL>` is the
   channel id and the `thread_ts` is that `p…` number with a dot inserted before
   the last six digits (`1748880000.123456`). Use `--battery PATH` to replay a
   different battery file (same markdown shape: top-level `- ` bullets are sent;
   headings, prose, and indented sub-bullets are skipped).
6. For each question the driver prints `[i/N]`, posts the answer + flag buttons
   into the thread, and waits. Read the reply in Slack; if it is wrong press a
   flag button (**correctness** / **formatting** / **investigate**). Press
   **Enter** in the terminal to send the next question.
7. When the battery is done, triage the flags with the
   `triage-flagged-interactions` skill (reads the same `logs/interactions.jsonl`).

Optional model override in `.env`:

```dotenv
OPENAI_MODEL=gpt-4o
```

## Development

Run checks with `uv`:

```bash
uv run pytest -q
uv run ruff check .
uv run pyright
```

Normal validation does not contact OpenAI.

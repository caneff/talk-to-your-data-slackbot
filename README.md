# Talk to Your Data Slackbot

Python project scaffold for a Slackbot that helps users talk to their data.

## Slack MVP scope

This repo's Slack Runtime Adapter is DM-only.

The MVP Demo Scenario also includes a no-secret local harness that simulates
Slack-like requests with a fake Question Interpreter provider, without any
Slack app, tokens, OpenAI secrets, or network calls.

Out of scope for this MVP:

- Channel mentions
- Slash commands
- Progress Updates
- Trust Detail follow-ups
- Public HTTP deployment

## Local demo

Run the no-secret local demo:

```bash
uv run python -m data_assistant.demo
```

The demo uses a tiny in-memory DuckDB `orders` table and prints:

- Slack-like happy path request
- Slack Acknowledgement status
- threaded Final Response
- Slack-like Non-Answer request
- threaded Non-Answer Response

The happy path uses the canonical January 2026 fixture with one missing
`region` and one missing `revenue`, so the Trust Summary shows both caveats.

## Optional manual Slack smoke test

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
uv run python -m data_assistant.slack_runtime
```

Startup requires `OPENAI_API_KEY`. Live provider failures, refusals, or invalid
structured output return the existing typed Non-Answer path; the runtime does
not fall back to a deterministic interpreter.

For local development, the runtime uses a tiny in-memory DuckDB `orders` table. It is only there to support a manual Slack smoke test. No dataset files are committed.

To run the same Slack bot against a different Semantic Layer and DuckDB
location, pass runtime data flags:

```bash
uv run python -m data_assistant.slack_runtime --semantic-layer-path examples/retail_ops_demo/semantic_layer --duckdb-path :memory: --seed-sql-path examples/retail_ops_demo/seeds/retail_ops_seed.sql
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

The container still runs `python -m data_assistant.slack_runtime`, so the Slack
app from `slack-app-manifest.yaml` is still required. Socket Mode opens an
outbound connection to Slack and binds no inbound port, so no `-p` flag is
needed for local Docker runs.

## Manual Slack smoke test

1. Start the adapter with `uv run python -m data_assistant.slack_runtime`.
2. Open a DM with the app in Slack.
3. Send a supported question. The local smoke-test data answers revenue
   by region, so use:
   `What was total revenue by region in January 2026?`
4. Verify the bot replies in the same thread as the original message timestamp.
5. Verify the reply is a Final Response with a Trust Summary.
6. Verify the reply answers from the local development data:
   `North: $1,500.00`
   `South: $800.00`
7. Send the safe Non-Answer question:
   `What was total revenue by region?`
8. Verify the bot replies with a Non-Answer Response that asks for clarification and includes a Trust Summary.

## Manual live Question Interpreter eval

Agent guard: do not run this or any other command that uses a real
`OPENAI_API_KEY` during normal development, validation, PR checks, or broad test
requests. Live OpenAI-backed commands cost API money and should run only when
the developer explicitly asks for that live run.

Run the provider-only live eval suite with `OPENAI_API_KEY` in `.env`:

```bash
uv run python -m data_assistant.question_interpreter.live_eval
```

Use verbose output to print expected and actual proposal details for passed
cases too:

```bash
uv run python -m data_assistant.question_interpreter.live_eval --verbose
```

Optional model override in `.env`:

```dotenv
OPENAI_MODEL=gpt-4o-mini
```

The suite sends real OpenAI requests for a small set of enabled passing cases
and compares raw `propose_question_frame(...)` meaning against exact expected:

- `intent`
- `metric`
- `dimension`
- `filters`
- `time_range.start_date`
- `time_range.end_date`

`time_range.label` is informational and ignored by the comparison.

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

## Development

Run checks with `uv`:

```bash
uv run pytest -q
uv run ruff check .
uv run pyright
```

Normal validation and the local demo do not contact OpenAI.

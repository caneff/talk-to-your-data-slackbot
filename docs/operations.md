# Running the Slackbot

How to configure, start, and host the Slackbot. To verify and evaluate it once
running, see [Evaluating the Slackbot](evaluation.md).

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
It is only there to support a [manual Slack acceptance
check](evaluation.md#manual-slack-acceptance-check). No DuckDB database file
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

Override the command only if you want the tiny local acceptance-check fixture instead:

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
[ADR-0013](adr/0013-demo-runs-via-local-docker-not-render.md).

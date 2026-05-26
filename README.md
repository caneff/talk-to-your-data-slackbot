# Talk to Your Data Slackbot

Python project scaffold for a Slackbot that helps users talk to their data.

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

For local development, the runtime uses a tiny in-memory DuckDB `orders` table. It is only there to support a manual Slack smoke test. No dataset files are committed.

## Manual smoke test

1. Start the adapter with `uv run python -m data_assistant.slack_runtime`.
2. Open a DM with the app in Slack.
3. Send the canonical question:
   `What was total revenue by region in January 2026?`
4. Verify the bot replies in the same thread as the original message timestamp.
5. Verify the reply is a Final Response with a Trust Summary.
6. Verify the reply answers from the local development data:
   `North: $1,500.00`
   `South: $800.00`
7. Send the safe Non-Answer question:
   `What was total revenue by region?`
8. Verify the bot replies with a Non-Answer Response that asks for clarification and includes a Trust Summary.

## Development

Run checks with `uv`:

```bash
uv run pytest -q
uv run ruff check .
uv run pyright
```

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

Create a Slack app and configure it for Socket Mode with Slack Bolt for Python.

Required app settings:

- Enable Socket Mode.
- Create an app-level token with the `connections:write` scope for `SLACK_APP_TOKEN`.
- Install the app to your workspace and use the bot token for `SLACK_BOT_TOKEN`.
- Enable Events and subscribe to the bot event `message.im`.
- Add bot scopes `chat:write` and `im:history`.
- In App Home, enable the Messages tab if your workspace needs it before users can DM the app.

Required environment variables:

```bash
export SLACK_BOT_TOKEN=...
export SLACK_APP_TOKEN=...
```

Use environment variables only. Do not commit token values, workspace IDs, or other secrets.

## Start the adapter

Install dependencies, export the Slack tokens, and start the local adapter:

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

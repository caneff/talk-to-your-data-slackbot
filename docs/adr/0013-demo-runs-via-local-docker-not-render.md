# The demo ships as a local Docker image, not a Render-hosted service

The **Slack Runtime Adapter** runs in Socket Mode: the process dials an
*outbound* WebSocket to Slack and binds no inbound port. To make the always-on
demo easy to spin up for two or three people, we package it as a Dockerfile that
anyone runs locally (`docker run` with the three secrets), and we do **not**
host it on Render. The image is the load-bearing artifact; if cloud hosting is
ever wanted, the same image deploys to a paid Render Background Worker without
change.

## Considered Options

We evaluated Render and rejected both of its tiers for this demo:

- **Free Web Service.** Render's free tier covers Web Services but not
  Background Workers ("Other service types don't support Free instances"). A Web
  Service "must bind to a port on host `0.0.0.0`" or "the deploy fails" — Socket
  Mode binds nothing, so it needs a dummy HTTP server just to deploy.
  Worse, Render "spins down a Free web service that goes 15 minutes without
  receiving any inbound traffic"; Socket Mode traffic is outbound, so a connected,
  working bot still shows zero inbound HTTP and gets spun down mid-demo. Keeping it
  awake requires an external pinger every <15 minutes, which then consumes nearly
  all of the 750 free instance-hours per month. The free tier is built for inbound
  web apps; an outbound-only bot is a poor fit at any effort.
- **Paid Background Worker.** The clean topology — a long-running process with no
  port, no spin-down. Rejected only on cost: it requires a paid instance (lowest
  paid tier, on the order of a few dollars a month) for a demo that two or three
  people touch occasionally. Not worth a standing charge.

Local Docker gives a $0, reproducible spin-up that mirrors the repo's uv
toolchain. Its one cost — the bot only answers while the operator's machine runs
the container — is acceptable because the demo is driven on demand, not expected
to be reachable when no one is presenting it.

## Consequences

- "Laptop-off reachability" is explicitly out of scope. Buying it later means
  paying for a Render Background Worker (or equivalent), not reworking the app.
- Whoever spins up the demo still needs the three secrets (`SLACK_BOT_TOKEN`,
  `SLACK_APP_TOKEN`, `OPENAI_API_KEY`) and a Slack app created from
  `slack-app-manifest.yaml`. Docker eases running the process, not Slack app
  setup, which remains the real friction.
- Live OpenAI cost is incurred per question for anyone with access to the Slack
  app while a container is running.

## Revisited / Narrowed

The original decision above still holds for **indefinite** hosting: an always-on
Render Background Worker is not worth a standing charge for a demo that two or
three people touch occasionally.

We are now carving out one narrow case. For a **time-boxed (~1 month) demo** the
paid Background Worker — previously rejected on standing cost — is a *sanctioned*
path. The small monthly cost (lowest paid tier) is accepted only for that demo
window. Nothing else changes: the existing Docker image deploys unchanged, the
Slack Socket Mode topology stays (outbound WebSocket, no inbound port, no queue,
no public request URL), and the free Web Service tier remains rejected for the
reasons above.

This ADR is **not** superseded. The boxed-demo path is documented in the README
("Host on Render (time-boxed demo)") and pinned as code in `render.yaml` at the
repo root, which fixes `type: worker` so nobody falls back into the free-tier Web
Service trap. When the demo window ends, the Worker is suspended or deleted so
the paid charge does not persist — restoring the original $0 default.

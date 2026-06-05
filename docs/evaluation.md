# Evaluating the Slackbot

Manual checks and live evals for the Slackbot. To get it running first, see
[Running the Slackbot](operations.md).

## Manual Slack acceptance check

This is an acceptance check, not a smoke test: it asserts answer correctness
(named store regions and money figures) and exercises both the Final Response
and Non-Answer branches, each with a Trust Summary. A smoke test would only
confirm the bot boots and replies in-thread without crashing (steps 1-4).

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
   > same dev config `slack_runtime` uses for the acceptance check), so it answers from
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

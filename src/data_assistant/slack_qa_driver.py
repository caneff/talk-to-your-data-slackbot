"""Manual Slack QA driver: replay the curated battery through the bot (#128).

This is a manual operator tool -- durable maintainer tooling run by hand, the
same category as the ``live_eval`` mains (not the product surface). It drives
the curated QA battery (``docs/qa-commerce-questions.md``) through the **real**
Slack Assistant answer path one question at a time, posting each rendered Final
Response **as the bot** into an assistant thread so a maintainer reads it and
presses the existing flag buttons. Flags land in the shared Interaction Log and
refill the ``triage-flagged-interactions`` pipeline with observed failures.

Approach B (see issue #128): the driver computes the answer via the shared
:meth:`~data_assistant.slack_assistant.AssistantAdapter.answer_and_render`
helper, appends the Interaction Log record, and posts the blocks + flag buttons
via the **bot token** (``chat.postMessage``). It does NOT synthesize a user
message, so it needs no user token, no manifest/scope change, and no reinstall.
Flag clicks are handled by the already-running bot's ``block_actions``
listeners over Socket Mode -- so the bot must be running and must share the same
``logs/interactions.jsonl`` path the driver writes.

Like the ``live_eval`` mains, ``main`` is near-untested by design: it talks to
live Slack and the live OpenAI answer path. Only :func:`parse_battery` (a pure
string -> list mapping) carries unit tests.
"""

from __future__ import annotations

import argparse
import collections.abc as collections_abc
import os
import pathlib
import sys
import typing

import dotenv

import data_assistant.slack_assistant as slack_assistant
import data_assistant.slack_runtime as slack_runtime

DEFAULT_BATTERY_PATH: typing.Final[str] = "docs/qa-commerce-questions.md"


def parse_battery(markdown: str) -> list[str]:
    """Extract the top-level ``- `` bullets from the QA battery markdown.

    Every line matching ``^- `` is a question to send; the bullet marker is
    stripped and surrounding whitespace trimmed. Headings (``#``), prose, and
    **indented** sub-bullets (``  - `` / ``\\t- ``) are maintainer reference only
    -- they are never sent and never auto-checked (the human is the only oracle,
    so there is deliberately no expected-answer comparison here). Pure string ->
    list: no Slack, no OpenAI.
    """
    questions: list[str] = []
    for line in markdown.splitlines():
        if line.startswith("- "):
            questions.append(line[len("- ") :].strip())
    return questions


def _quietly_set_status(status: str) -> None:
    """No-op progress sink: the driver does not surface staged status."""
    del status


def _build_web_client(token: str) -> typing.Any:
    # Typed as Any: slack_sdk's WebClient methods are loosely typed and would
    # otherwise leak "partially unknown" through this manual driver, the same
    # rationale the Bolt wiring shim uses in slack_assistant.py.
    from slack_sdk import WebClient

    return WebClient(token=token)


def main(
    argv: collections_abc.Sequence[str] = (),
    *,
    env_file: str | pathlib.Path = ".env",
) -> int:
    """Replay the battery through the bot, one question at a time (lockstep).

    For each parsed question: run the shared ``answer_and_render`` helper (same
    answer path + same Interaction Log path the running bot uses), post the
    rendered blocks + flag buttons into the assistant thread as the bot, then
    wait for the operator to press Enter before the next question. Costs real
    OpenAI tokens per question; never run this in tests or CI.
    """
    args = _parse_args(argv)
    dotenv.load_dotenv(dotenv_path=args.env_file or env_file, override=False)
    environ = os.environ

    bot_token = environ.get("SLACK_BOT_TOKEN")
    if not bot_token:
        print("Missing required environment variable: SLACK_BOT_TOKEN", file=sys.stderr)
        return 1

    battery_text = pathlib.Path(args.battery).read_text(encoding="utf-8")
    questions = parse_battery(battery_text)
    if not questions:
        print(f"No questions found in battery {args.battery}.", file=sys.stderr)
        return 1

    client = _build_web_client(bot_token)
    adapter = slack_assistant.AssistantAdapter(
        connection_factory=_connection_factory(args),
        answer_path=slack_runtime.build_openai_answer_path(environ),
        internal_identity_resolver=slack_assistant.dev_identity,
        model_label=slack_runtime.resolve_model_label(environ),
        log_path=slack_runtime.resolve_interaction_log_path(environ),
    )

    print(
        f"Replaying {len(questions)} question(s) from {args.battery} "
        f"into channel={args.channel} thread_ts={args.thread_ts} as the bot.\n"
        "The bot must be running to own the flag buttons and share the log.\n"
    )
    for index, question in enumerate(questions, start=1):
        print(f"[{index}/{len(questions)}] {question}")
        _interaction_id, final_response, reply_blocks = adapter.answer_and_render(
            text=question,
            user="qa_driver",
            set_status=_quietly_set_status,
        )
        client.chat_postMessage(
            channel=args.channel,
            thread_ts=args.thread_ts,
            text=final_response.text,
            blocks=list(reply_blocks),
        )
        input("  posted. Press Enter for the next question... ")

    return 0


def _connection_factory(args: argparse.Namespace) -> slack_runtime.ConnectionFactory:
    if args.duckdb_path is None:
        return slack_runtime.dev_connection_factory
    return slack_runtime.build_duckdb_connection_factory(
        args.duckdb_path,
        seed_sql_path=args.seed_sql_path,
    )


def _parse_args(argv: collections_abc.Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Replay the curated QA battery through the bot into an assistant "
            "thread for human flagging (manual operator tool)."
        ),
    )
    parser.add_argument(
        "--channel",
        required=True,
        help="Channel id of the assistant thread to post answers into.",
    )
    parser.add_argument(
        "--thread-ts",
        required=True,
        help="thread_ts of the assistant thread to post answers into.",
    )
    parser.add_argument(
        "--battery",
        type=str,
        default=DEFAULT_BATTERY_PATH,
        help=f"Markdown battery to replay. Defaults to {DEFAULT_BATTERY_PATH}.",
    )
    parser.add_argument(
        "--env-file",
        type=pathlib.Path,
        default=None,
        help="dotenv file to load before startup. Defaults to .env.",
    )
    parser.add_argument(
        "--duckdb-path",
        type=str,
        default=None,
        help="DuckDB database location to use instead of the tiny dev fixture.",
    )
    parser.add_argument(
        "--seed-sql-path",
        type=pathlib.Path,
        default=None,
        help="Optional SQL file to run whenever the DuckDB connection opens.",
    )
    args = parser.parse_args(argv)
    if args.seed_sql_path is not None and args.duckdb_path is None:
        parser.error("--seed-sql-path requires --duckdb-path")
    return args


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

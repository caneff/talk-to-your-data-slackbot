"""Manual Slack QA driver: replay the curated battery through the bot (#128).

This is a manual operator tool -- durable maintainer tooling run by hand, the
same category as the ``live_eval`` mains (not the product surface). It drives
the curated QA battery (``docs/qa-retail-questions.md``) through the **real**
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
``logs/interactions.jsonl`` path the driver writes. The driver also
auto-discovers which assistant thread to post into from the pointer the bot
writes on ``thread_started`` (``logs/last_assistant_thread.json``), so
``--channel``/``--thread-ts`` are optional explicit overrides.

Like the ``live_eval`` mains, ``main`` is near-untested by design: it talks to
live Slack and the live OpenAI answer path. Only :func:`parse_battery` (a pure
string -> list mapping) carries unit tests.
"""

from __future__ import annotations

import argparse
import collections.abc as collections_abc
import dataclasses
import json
import os
import pathlib
import re
import subprocess
import sys
import typing

import dotenv

import data_assistant.assistant_thread_pointer as assistant_thread_pointer
import data_assistant.known_qa_issues as known_qa_issues
import data_assistant.semantic_layer.loader as semantic_layer_loader
import data_assistant.slack_assistant as slack_assistant
import data_assistant.slack_runtime as slack_runtime

DEFAULT_BATTERY_PATH: typing.Final[str] = "docs/qa-retail-questions.md"

_NO_THREAD_MESSAGE: typing.Final[str] = (
    "No assistant thread found — open a thread with the bot first, "
    "or pass --channel/--thread-ts."
)
_IDENTIFIED_CASE_PATTERN: typing.Final[re.Pattern[str]] = re.compile(
    r"^\[(?P<id>[^\]]+)\]\s+(?P<question>.+)$"
)


@dataclasses.dataclass(frozen=True)
class QACase:
    id: str | None
    question: str


def parse_battery_cases(
    markdown: str,
    *,
    allow_unidentified: bool = False,
) -> list[QACase]:
    """Extract top-level QA cases from markdown in source order."""
    cases: list[QACase] = []
    seen_ids: set[str] = set()
    for line in markdown.splitlines():
        if not line.startswith("- "):
            continue
        bullet_text = line[len("- ") :].strip()
        match = _IDENTIFIED_CASE_PATTERN.match(bullet_text)
        if match is None:
            if allow_unidentified:
                cases.append(QACase(id=None, question=bullet_text))
                continue
            raise ValueError(
                "Missing QA case id for bullet: "
                f"{bullet_text}. Use '- [qa-case-id] Question text' or pass "
                "--allow-unidentified-cases."
            )
        case_id = match.group("id").strip()
        if case_id in seen_ids:
            raise ValueError(f"Duplicate QA case id: {case_id}")
        seen_ids.add(case_id)
        cases.append(QACase(id=case_id, question=match.group("question").strip()))
    return cases


def parse_battery(markdown: str) -> list[str]:
    """Extract the top-level ``- `` bullets from the QA battery markdown.

    Every line matching ``^- `` is a question to send; the bullet marker is
    stripped and surrounding whitespace trimmed. Headings (``#``), prose, and
    **indented** sub-bullets (``  - `` / ``\\t- ``) are maintainer reference only
    -- they are never sent and never auto-checked (the human is the only oracle,
    so there is deliberately no expected-answer comparison here). Pure string ->
    list: no Slack, no OpenAI.
    """
    return [
        case.question for case in parse_battery_cases(markdown, allow_unidentified=True)
    ]


def resolve_known_issues_path(
    *,
    battery_path: pathlib.Path,
    known_issues_path: pathlib.Path | None,
) -> pathlib.Path:
    """Resolve the Known QA Issue sidecar path for one battery."""
    if known_issues_path is not None:
        return known_issues_path
    return known_qa_issues.default_sidecar_path(battery_path)


def preflight_known_issues(
    *,
    battery_path: pathlib.Path,
    cases: collections_abc.Sequence[QACase],
    known_issues_path: pathlib.Path | None,
    skip_prune: bool,
    is_issue_open: collections_abc.Callable[[int], bool] | None = None,
) -> None:
    """Create, validate, and optionally prune the Known QA Issue sidecar."""
    if any(case.id is None for case in cases):
        return

    sidecar_path = resolve_known_issues_path(
        battery_path=battery_path,
        known_issues_path=known_issues_path,
    )
    case_ids = [typing.cast("str", case.id) for case in cases]
    sidecar = known_qa_issues.load_sidecar(
        sidecar_path,
        valid_case_ids=case_ids,
        create_if_missing=True,
    )
    if skip_prune:
        return
    issue_is_open = is_issue_open or _github_issue_is_open
    pruned = known_qa_issues.prune_sidecar(
        sidecar,
        valid_case_ids=case_ids,
        is_issue_open=issue_is_open,
    )
    if pruned != sidecar:
        known_qa_issues.write_sidecar(sidecar_path, pruned)


def resolve_thread_target(
    *,
    channel: str | None,
    thread_ts: str | None,
    pointer_path: pathlib.Path = assistant_thread_pointer.DEFAULT_POINTER_PATH,
) -> tuple[str, str] | str:
    """Decide which assistant thread to post into: explicit args, else pointer.

    Explicit ``--channel``/``--thread-ts`` always win. Any id left unset is
    filled from the auto-discovery pointer (``last_assistant_thread.json``) the
    running bot wrote on ``thread_started`` -- last-writer-wins, so it resolves
    to the most recently opened thread. Returns ``(channel, thread_ts)`` when
    both are resolved, or an operator-facing error message string when they are
    not. Pure (only reads the injected pointer file) so it is unit-tested
    without Slack.
    """
    pointer = assistant_thread_pointer.read_latest(pointer_path) or (None, None)
    pointer_channel, pointer_thread_ts = pointer
    resolved_channel = channel or pointer_channel
    resolved_thread_ts = thread_ts or pointer_thread_ts
    if resolved_channel and resolved_thread_ts:
        return resolved_channel, resolved_thread_ts
    return _NO_THREAD_MESSAGE


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

    battery_text = pathlib.Path(args.battery).read_text(encoding="utf-8")
    try:
        cases = parse_battery_cases(
            battery_text,
            allow_unidentified=args.allow_unidentified_cases,
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    if not cases:
        print(f"No questions found in battery {args.battery}.", file=sys.stderr)
        return 1
    try:
        preflight_known_issues(
            battery_path=pathlib.Path(args.battery),
            cases=cases,
            known_issues_path=args.known_issues_path,
            skip_prune=args.skip_known_issue_prune,
        )
    except (ValueError, known_qa_issues.KnownQAIssuePruneError) as exc:
        print(str(exc), file=sys.stderr)
        return 1

    bot_token = environ.get("SLACK_BOT_TOKEN")
    if not bot_token:
        print("Missing required environment variable: SLACK_BOT_TOKEN", file=sys.stderr)
        return 1

    target = resolve_thread_target(channel=args.channel, thread_ts=args.thread_ts)
    if isinstance(target, str):
        print(target, file=sys.stderr)
        return 1
    channel, thread_ts = target

    client = _build_web_client(bot_token)
    semantic_layer = semantic_layer_loader.load_semantic_layer(args.semantic_layer_path)
    adapter = slack_assistant.AssistantAdapter(
        connection_factory=_connection_factory(args),
        answer_path=slack_runtime.build_openai_answer_path(
            environ, semantic_layer=semantic_layer
        ),
        internal_identity_resolver=slack_assistant.dev_identity,
        model_label=slack_runtime.resolve_model_label(environ),
        log_path=slack_runtime.resolve_interaction_log_path(environ),
    )

    print(
        f"Replaying {len(cases)} question(s) from {args.battery} "
        f"into channel={channel} thread_ts={thread_ts} as the bot.\n"
        "The bot must be running to own the flag buttons and share the log.\n"
    )
    for index, case in enumerate(cases, start=1):
        case_label = (
            f"{case.question} ({case.id})" if case.id is not None else case.question
        )
        print(f"[{index}/{len(cases)}] {case_label}")
        _interaction_id, final_response, reply_blocks = adapter.answer_and_render(
            text=case.question,
            user="qa_driver",
            set_status=_quietly_set_status,
        )
        client.chat_postMessage(
            channel=channel,
            thread_ts=thread_ts,
            text=final_response.text,
            blocks=list(reply_blocks),
        )
        input("  posted. Press Enter for the next question... ")

    return 0


def _connection_factory(args: argparse.Namespace) -> slack_runtime.ConnectionFactory:
    # No flags: build the retail app-run default (retail seed in :memory:),
    # consuming the shared retail path constants from slack_runtime so there is
    # exactly one source of truth for the retail paths. An explicit --duckdb-path
    # opts out of the retail seed unless --seed-sql-path is also given.
    if args.duckdb_path is None:
        return slack_runtime.build_duckdb_connection_factory(
            slack_runtime.RETAIL_DUCKDB_PATH,
            seed_sql_path=slack_runtime.RETAIL_SEED_SQL_PATH,
        )
    return slack_runtime.build_duckdb_connection_factory(
        args.duckdb_path,
        seed_sql_path=args.seed_sql_path,
    )


def _github_issue_is_open(issue_number: int) -> bool:
    """Return whether one GitHub issue is still open via ``gh issue view``."""
    completed = subprocess.run(
        ["gh", "issue", "view", str(issue_number), "--json", "state"],
        capture_output=True,
        check=True,
        cwd=pathlib.Path(__file__).resolve().parents[2],
        text=True,
    )
    payload = typing.cast("dict[str, object]", json.loads(completed.stdout))
    return payload.get("state") == "OPEN"


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Replay the curated QA battery through the bot into an assistant "
            "thread for human flagging (manual operator tool)."
        ),
    )
    parser.add_argument(
        "--channel",
        default=None,
        help=(
            "Channel id of the assistant thread to post answers into. "
            "Defaults to the most recently opened thread auto-discovered from "
            "the bot's pointer file."
        ),
    )
    parser.add_argument(
        "--thread-ts",
        default=None,
        help=(
            "thread_ts of the assistant thread to post answers into. "
            "Defaults to the most recently opened thread auto-discovered from "
            "the bot's pointer file."
        ),
    )
    parser.add_argument(
        "--battery",
        type=str,
        default=DEFAULT_BATTERY_PATH,
        help=f"Markdown battery to replay. Defaults to {DEFAULT_BATTERY_PATH}.",
    )
    parser.add_argument(
        "--allow-unidentified-cases",
        action="store_true",
        help=(
            "Allow legacy top-level '- Question text' bullets without "
            "stable QA case ids."
        ),
    )
    parser.add_argument(
        "--known-issues-path",
        type=pathlib.Path,
        default=None,
        help=(
            "Known QA Issue sidecar path. Defaults to the battery path with "
            "its suffix replaced by .known-issues.json."
        ),
    )
    parser.add_argument(
        "--skip-known-issue-prune",
        action="store_true",
        help=(
            "Skip preflight pruning of closed or stale Known QA Issue entries "
            "before posting any Slack messages."
        ),
    )
    parser.add_argument(
        "--env-file",
        type=pathlib.Path,
        default=None,
        help="dotenv file to load before startup. Defaults to .env.",
    )
    parser.add_argument(
        "--semantic-layer-path",
        type=pathlib.Path,
        default=slack_runtime.RETAIL_SEMANTIC_LAYER_PATH,
        help=(
            "Semantic Layer directory to load. Defaults to the retail app-run "
            "layer (examples/retail_ops_demo/semantic_layer/)."
        ),
    )
    parser.add_argument(
        "--duckdb-path",
        type=str,
        default=None,
        help=(
            "DuckDB database location. Defaults to an in-memory database seeded "
            "with the retail demo data."
        ),
    )
    parser.add_argument(
        "--seed-sql-path",
        type=pathlib.Path,
        default=None,
        help=(
            "SQL file to run whenever the DuckDB connection opens. Defaults to "
            "the retail demo seed (only when --duckdb-path is also unset)."
        ),
    )
    return parser


def _parse_args(argv: collections_abc.Sequence[str]) -> argparse.Namespace:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    if args.seed_sql_path is not None and args.duckdb_path is None:
        parser.error("--seed-sql-path requires --duckdb-path")
    return args


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

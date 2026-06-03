"""Live Provider Proposal Eval CLI that builds the real OpenAI provider."""

from __future__ import annotations

import argparse
import collections.abc
import dataclasses
import os
import pathlib
import sys
import typing

import dotenv

import data_assistant.composition as composition
import data_assistant.question_interpreter as question_interpreter
import data_assistant.question_interpreter.provider_proposal_eval as proposal_eval
import data_assistant.semantic_layer.loader as semantic_layer_loader


def main(
    *,
    stdout: typing.TextIO = sys.stdout,
    stderr: typing.TextIO = sys.stderr,
    environ: collections.abc.Mapping[str, str] | None = None,
    env_file: str | pathlib.Path = ".env",
    argv: collections.abc.Sequence[str] = (),
) -> int:
    """Run Provider Proposal Eval against real OpenAI provider config."""
    args = _parse_args(argv)
    active_environ = environ
    if active_environ is None:
        _load_env_file(env_file)
        active_environ = os.environ

    try:
        provider = question_interpreter.build_openai_question_interpreter_provider(
            active_environ
        )
    except question_interpreter.OpenAIQuestionInterpreterConfigError as error:
        print(str(error), file=stderr)
        return 1

    failures_path = _resolve_failures_path(args.failures_out)
    failures_path.parent.mkdir(parents=True, exist_ok=True)
    failures_file = failures_path.open("w", encoding="utf-8")
    try:
        report = proposal_eval.run_provider_proposal_eval(
            provider=provider,
            semantic_layer=semantic_layer_loader.load_semantic_layer(
                composition.RETAIL_SEMANTIC_LAYER_PATH
            ),
            sample_count=args.samples,
            progress=args.progress,
            progress_file=stderr,
            failures_file=failures_file,
            start_at=args.start_at,
            stop_at=args.stop_at,
            only_cases=args.only_cases,
        )
    except ValueError as error:
        print(str(error), file=stderr)
        return 1
    finally:
        failures_file.close()
    _write_selection_notice(stdout=stdout, args=args, report=report)
    proposal_eval.write_provider_proposal_eval_report(
        stdout=stdout,
        report=report,
        verbose=args.verbose,
    )
    if report.failed or report.tripwires:
        return 1
    return 0


@dataclasses.dataclass(frozen=True)
class _CliArgs:
    verbose: bool
    progress: bool
    samples: int
    failures_out: str | None
    start_at: int
    stop_at: int | None
    only_cases: tuple[str, ...] | None


def _parse_args(argv: collections.abc.Sequence[str]) -> _CliArgs:
    parser = argparse.ArgumentParser(
        description="Run live Provider Proposal Eval for OpenAI provider output.",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="print full expected and actual details for passed cases",
    )
    parser.add_argument(
        "--no-progress",
        action="store_true",
        help="disable the live case progress bar",
    )
    parser.add_argument(
        "--samples",
        type=int,
        default=proposal_eval.DEFAULT_SAMPLE_COUNT,
        help=(
            "number of provider samples per case for flake hunting "
            f"(default {proposal_eval.DEFAULT_SAMPLE_COUNT}); try "
            "--samples 10 to surface rare flakes"
        ),
    )
    parser.add_argument(
        "--failures-out",
        default=None,
        help=(
            "path for the streamed failures JSONL (default: a timestamped file "
            f"under {proposal_eval.DEFAULT_FAILURES_DIR}/); a clean run "
            "leaves an empty file"
        ),
    )
    parser.add_argument(
        "--start-at",
        type=int,
        default=1,
        help="1-based enabled-case index to start at (default 1)",
    )
    parser.add_argument(
        "--stop-at",
        type=int,
        default=None,
        help="1-based enabled-case index to stop at (inclusive; default last)",
    )
    parser.add_argument(
        "--only-cases",
        action="append",
        default=None,
        help=(
            "run only these enabled cases by 1-based index or name "
            "(comma-separated and/or repeatable); mutually exclusive with "
            "--start-at/--stop-at"
        ),
    )
    args = parser.parse_args(list(argv))
    only_cases = _parse_only_cases(typing.cast("list[str] | None", args.only_cases))
    start_at = typing.cast(int, args.start_at)
    stop_at = typing.cast("int | None", args.stop_at)
    if only_cases is not None and (start_at != 1 or stop_at is not None):
        parser.error("--only-cases cannot be combined with --start-at or --stop-at")
    return _CliArgs(
        verbose=typing.cast(bool, args.verbose),
        progress=not typing.cast(bool, args.no_progress),
        samples=typing.cast(int, args.samples),
        failures_out=typing.cast("str | None", args.failures_out),
        start_at=start_at,
        stop_at=stop_at,
        only_cases=only_cases,
    )


def _parse_only_cases(raw: list[str] | None) -> tuple[str, ...] | None:
    if raw is None:
        return None
    tokens = tuple(
        token.strip() for entry in raw for token in entry.split(",") if token.strip()
    )
    return tokens


def _load_env_file(path: str | pathlib.Path = ".env") -> None:
    dotenv.load_dotenv(dotenv_path=path, override=False)


def _resolve_failures_path(failures_out: str | None) -> pathlib.Path:
    if failures_out is not None:
        return pathlib.Path(failures_out)
    return proposal_eval.resolve_default_failures_path()


def _write_selection_notice(
    *,
    stdout: typing.TextIO,
    args: _CliArgs,
    report: proposal_eval.ProviderProposalEvalReport,
) -> None:
    enabled_count = sum(1 for case in proposal_eval.DEFAULT_CASES if case.enabled)
    if args.only_cases is not None:
        stdout.write(
            f"Ran {report.total} selected of {enabled_count} enabled (--only-cases)\n"
        )
        return
    if args.start_at != 1 or args.stop_at is not None:
        stdout.write(
            f"Started at case {args.start_at} "
            f"(running {report.total} of {enabled_count} enabled)\n"
        )


if __name__ == "__main__":
    raise SystemExit(main(argv=sys.argv[1:]))

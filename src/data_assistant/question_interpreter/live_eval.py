"""Compatibility wrapper for old live eval imports and CLI.

Use `data_assistant.question_interpreter.provider_proposal_eval` for the pure
injected-provider harness and
`data_assistant.question_interpreter.live_provider_proposal_eval` for the live
OpenAI-backed CLI entrypoint.
"""

from __future__ import annotations

import collections.abc
import pathlib
import sys
import typing

from data_assistant.question_interpreter import (
    live_provider_proposal_eval,
)
from data_assistant.question_interpreter.provider_proposal_eval import (
    DEFAULT_CASES,
    DEFAULT_FAILURES_DIR,
    DEFAULT_SAMPLE_COUNT,
    ProviderProposalEvalCase,
    ProviderProposalEvalFailure,
    ProviderProposalEvalPass,
    ProviderProposalEvalReport,
    ProviderResult,
    compare_provider_proposal_meaning,
    resolve_default_failures_path,
    run_provider_proposal_eval,
    select_cases,
    write_provider_proposal_eval_report,
)

LiveEvalCase = ProviderProposalEvalCase
LiveEvalFailure = ProviderProposalEvalFailure
LiveEvalPass = ProviderProposalEvalPass
LiveEvalReport = ProviderProposalEvalReport
compare_question_frame_meaning = compare_provider_proposal_meaning
run_live_question_interpreter_eval = run_provider_proposal_eval
write_live_eval_report = write_provider_proposal_eval_report
_resolve_failures_path = resolve_default_failures_path


def main(
    *,
    stdout: typing.TextIO = sys.stdout,
    stderr: typing.TextIO = sys.stderr,
    environ: collections.abc.Mapping[str, str] | None = None,
    env_file: str | pathlib.Path = ".env",
    argv: collections.abc.Sequence[str] = (),
) -> int:
    return live_provider_proposal_eval.main(
        stdout=stdout,
        stderr=stderr,
        environ=environ,
        env_file=env_file,
        argv=argv,
    )


__all__ = [
    "DEFAULT_CASES",
    "DEFAULT_FAILURES_DIR",
    "DEFAULT_SAMPLE_COUNT",
    "LiveEvalCase",
    "LiveEvalFailure",
    "LiveEvalPass",
    "LiveEvalReport",
    "ProviderProposalEvalCase",
    "ProviderProposalEvalFailure",
    "ProviderProposalEvalPass",
    "ProviderProposalEvalReport",
    "ProviderResult",
    "compare_provider_proposal_meaning",
    "compare_question_frame_meaning",
    "main",
    "resolve_default_failures_path",
    "run_live_question_interpreter_eval",
    "run_provider_proposal_eval",
    "select_cases",
    "write_live_eval_report",
    "write_provider_proposal_eval_report",
]

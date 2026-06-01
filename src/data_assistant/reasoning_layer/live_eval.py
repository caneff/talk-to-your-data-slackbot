"""Manual live eval suite for the OpenAI-backed Reasoning Layer.

Mirrors the Question Interpreter live eval mechanics (k=3 sampling, all-pass,
per-case pass-rate, non-zero exit), but the comparator asserts grounding
properties on the narrative proposal rather than prose exact-match.

The live entry point (``main``) is run manually by the user against a real
``OPENAI_API_KEY``; the suite never calls the live API from automated tests.
"""

from __future__ import annotations

import argparse
import collections.abc
import dataclasses
import os
import pathlib
import sys
import typing

import dotenv
import tqdm

import data_assistant.reasoning_layer as reasoning_layer
import data_assistant.reasoning_layer.narrative_cases as narrative_cases
import data_assistant.reasoning_layer.proposals as proposals

ProviderResult: typing.TypeAlias = (
    reasoning_layer.NarrativeProposal | reasoning_layer.ProviderFailure
)

# Headline slot whose computed value-string must survive into the filled
# summary. Only the headline ``{metric_total}`` is in the safety-only bar; the
# leader clause (`{top_dimension} at {top_value}`) is stylistic, so terser
# prose that omits it passes (see ADR-0012).
_VALUE_SLOTS: tuple[str, ...] = ("metric_total",)


@dataclasses.dataclass(frozen=True)
class LiveEvalFailure:
    """One failed live eval case."""

    case_name: str
    reasons: tuple[str, ...]
    pass_count: int = 0
    sample_count: int = 1


@dataclasses.dataclass(frozen=True)
class LiveEvalPass:
    """One passed live eval case."""

    case_name: str
    pass_count: int = 1
    sample_count: int = 1


@dataclasses.dataclass(frozen=True)
class LiveEvalReport:
    """Aggregate live eval results."""

    total: int
    passes: tuple[LiveEvalPass, ...]
    failures: tuple[LiveEvalFailure, ...]

    @property
    def passed(self) -> int:
        return len(self.passes)

    @property
    def failed(self) -> int:
        return len(self.failures)


DEFAULT_CASES = narrative_cases.SHARED_NARRATIVE_CASES
DEFAULT_SAMPLE_COUNT = 3


def compare_grounding(
    *,
    proposal: ProviderResult,
    expectation: narrative_cases.GroundingExpectation,
    slot_values: dict[str, object],
) -> tuple[str, ...]:
    """Return grounding-property mismatches for one proposal.

    The all-pass (k=3) bar is a safety-only property set: grounded (zero
    digits) + fillable + the headline ``{metric_total}`` value survives into
    the filled prose. The optional leader clause is stylistic, so safe-but-
    terser prose that omits it still passes (see ADR-0012).
    """
    if isinstance(proposal, reasoning_layer.ProviderFailure):
        return (f"provider failure: {proposal.reason}",)
    reasons: list[str] = []
    if not proposals.proposal_is_grounded(proposal):
        reasons.append("proposal is not grounded: prose contains a digit")
    filled = proposals.fill_narrative(proposal, slot_values)
    if filled is None:
        reasons.append("proposal is not fillable: references an unknown slot")
    for required_slot in expectation.required_slots:
        if required_slot not in proposal.summary:
            reasons.append(
                f"required slot {required_slot} missing from proposal summary"
            )
    if filled is not None:
        for slot_name in _VALUE_SLOTS:
            value = str(slot_values.get(slot_name, ""))
            if value and value not in filled:
                reasons.append(f"computed value {value} absent from filled summary")
    return tuple(reasons)


def run_live_reasoning_eval(
    *,
    provider: reasoning_layer.ReasoningProvider,
    cases: collections.abc.Iterable[
        narrative_cases.SharedNarrativeCase
    ] = DEFAULT_CASES,
    sample_count: int = DEFAULT_SAMPLE_COUNT,
    progress: bool = False,
    progress_file: typing.TextIO | None = None,
) -> LiveEvalReport:
    """Run all enabled live eval cases k times and aggregate failures."""
    if sample_count < 1:
        raise ValueError("sample_count must be at least 1")
    enabled_cases = tuple(case for case in cases if case.enabled)
    passes: list[LiveEvalPass] = []
    failures: list[LiveEvalFailure] = []
    progress_bar = _new_case_progress_bar(
        enabled=progress,
        total=len(enabled_cases),
        progress_file=progress_file,
    )
    try:
        for case_index, case in enumerate(enabled_cases, start=1):
            _set_case_progress(
                progress_bar=progress_bar,
                case_index=case_index,
                total=len(enabled_cases),
                case_name=case.name,
            )
            slot_values = proposals.compute_slot_values(case.prepared_data)
            result_shape = proposals.figure_free_result_shape(slot_values)
            pass_count = 0
            sample_failures: list[str] = []
            for sample_index in range(sample_count):
                proposal = provider.propose_narrative(result_shape=result_shape)
                reasons = compare_grounding(
                    proposal=proposal,
                    expectation=case.expectation,
                    slot_values=slot_values,
                )
                if reasons:
                    sample_failures.extend(
                        f"sample {sample_index + 1}: {reason}" for reason in reasons
                    )
                    continue
                pass_count += 1
            if sample_failures:
                failures.append(
                    LiveEvalFailure(
                        case_name=case.name,
                        reasons=tuple(sample_failures),
                        pass_count=pass_count,
                        sample_count=sample_count,
                    )
                )
                _update_case_progress(progress_bar)
                continue
            passes.append(
                LiveEvalPass(
                    case_name=case.name,
                    pass_count=pass_count,
                    sample_count=sample_count,
                )
            )
            _update_case_progress(progress_bar)
    finally:
        if progress_bar is not None:
            progress_bar.close()
    return LiveEvalReport(
        total=len(enabled_cases),
        passes=tuple(passes),
        failures=tuple(failures),
    )


def write_live_eval_report(
    *,
    stdout: typing.TextIO,
    report: LiveEvalReport,
) -> None:
    """Print aggregate results and detailed failures."""
    stdout.write(f"Total cases: {report.total}\n")
    stdout.write(f"Passed: {report.passed}\n")
    stdout.write(f"Failed: {report.failed}\n")
    for passed_case in report.passes:
        stdout.write(
            f"[PASS] {passed_case.case_name} "
            f"(pass rate: {passed_case.pass_count}/{passed_case.sample_count})\n"
        )
    for failure in report.failures:
        stdout.write(
            f"[FAIL] {failure.case_name} "
            f"(pass rate: {failure.pass_count}/{failure.sample_count})\n"
        )
        for reason in failure.reasons:
            stdout.write(f"Reason: {reason}\n")


def main(
    *,
    stdout: typing.TextIO = sys.stdout,
    stderr: typing.TextIO = sys.stderr,
    environ: collections.abc.Mapping[str, str] | None = None,
    env_file: str | pathlib.Path = ".env",
    argv: collections.abc.Sequence[str] = (),
) -> int:
    """Run the manual live eval suite against the real OpenAI provider config."""
    args = _parse_args(argv)
    active_environ = environ
    if active_environ is None:
        dotenv.load_dotenv(dotenv_path=env_file, override=False)
        active_environ = os.environ

    try:
        provider = reasoning_layer.build_openai_reasoning_provider(active_environ)
    except reasoning_layer.OpenAIReasoningConfigError as error:
        print(str(error), file=stderr)
        return 1

    report = run_live_reasoning_eval(
        provider=provider,
        progress=args.progress,
        progress_file=stderr,
    )
    write_live_eval_report(stdout=stdout, report=report)
    if report.failed:
        return 1
    return 0


@dataclasses.dataclass(frozen=True)
class _CliArgs:
    progress: bool


def _parse_args(argv: collections.abc.Sequence[str]) -> _CliArgs:
    parser = argparse.ArgumentParser(
        description="Run manual live evals for OpenAI Reasoning Layer output.",
    )
    parser.add_argument(
        "--no-progress",
        action="store_true",
        help="disable the live case progress bar",
    )
    args = parser.parse_args(list(argv))
    return _CliArgs(progress=not typing.cast(bool, args.no_progress))


def _new_case_progress_bar(
    *,
    enabled: bool,
    total: int,
    progress_file: typing.TextIO | None,
) -> typing.Any | None:
    if not enabled:
        return None
    return tqdm.tqdm(
        total=total,
        file=progress_file,
        leave=False,
        dynamic_ncols=True,
        bar_format="{desc} |{bar}| {percentage:3.0f}%",
    )


def _set_case_progress(
    *,
    progress_bar: typing.Any | None,
    case_index: int,
    total: int,
    case_name: str,
) -> None:
    if progress_bar is None:
        return
    progress_bar.set_description_str(
        f"Live eval cases {case_index}/{total}: {case_name}",
        refresh=True,
    )


def _update_case_progress(progress_bar: typing.Any | None) -> None:
    if progress_bar is None:
        return
    progress_bar.update(1)


if __name__ == "__main__":
    raise SystemExit(main())

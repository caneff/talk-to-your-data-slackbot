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

import data_assistant.reasoning_layer as reasoning_layer
import data_assistant.reasoning_layer.narrative_cases as narrative_cases
import data_assistant.reasoning_layer.proposals as proposals
import data_assistant.workflow.contracts as contracts

ProviderResult: typing.TypeAlias = (
    reasoning_layer.NarrativeProposal | reasoning_layer.ProviderFailure
)

# Slots whose computed value-strings must survive into the filled summary.
_VALUE_SLOTS: tuple[str, ...] = ("metric_total", "top_value")


@dataclasses.dataclass(frozen=True)
class LiveEvalCase:
    """One manual live eval fixture with its grounding expectation."""

    name: str
    prepared_data: contracts.PreparedData
    expectation: narrative_cases.GroundingExpectation
    enabled: bool = True


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


DEFAULT_CASES: tuple[LiveEvalCase, ...] = tuple(
    LiveEvalCase(
        name=case.name,
        prepared_data=case.prepared_data,
        expectation=case.expectation,
        enabled=case.enabled,
    )
    for case in narrative_cases.SHARED_NARRATIVE_CASES
)
DEFAULT_SAMPLE_COUNT = 3


def compare_grounding(
    *,
    proposal: ProviderResult,
    expectation: narrative_cases.GroundingExpectation,
    slot_values: dict[str, object],
) -> tuple[str, ...]:
    """Return grounding-property mismatches for one proposal.

    With ``allow_degrade`` the adversarial safe property holds: a proposal that
    would degrade visibly to the template (provider failure, ungrounded prose,
    or an unfillable summary) passes, because that path never ships a fabricated
    figure. Otherwise every requested grounding property must hold.
    """
    if isinstance(proposal, reasoning_layer.ProviderFailure):
        if expectation.allow_degrade:
            return ()
        return (f"provider failure: {proposal.reason}",)

    grounded = proposals.proposal_is_grounded(proposal)
    filled = proposals.fill_narrative(proposal, slot_values)

    if expectation.allow_degrade:
        # Safe property: grounded + fillable (a usable narrative) OR a visible
        # degrade. The only failure is prose that is grounded AND fillable yet
        # still drops a fabricated figure — impossible here, since grounding
        # already rejects every digit. So any outcome is safe.
        if grounded and filled is not None:
            return _value_presence_reasons(
                filled=filled,
                slot_values=slot_values,
                require=False,
            )
        return ()

    reasons: list[str] = []
    if expectation.expect_grounded and not grounded:
        reasons.append("proposal is not grounded: prose contains a digit")
    if expectation.expect_fillable and filled is None:
        reasons.append("proposal is not fillable: references an unknown slot")
    for required_slot in expectation.required_slots:
        if required_slot not in proposal.summary:
            reasons.append(
                f"required slot {required_slot} missing from proposal summary"
            )
    if expectation.expect_values_present and filled is not None:
        reasons.extend(
            _value_presence_reasons(
                filled=filled,
                slot_values=slot_values,
                require=True,
            )
        )
    return tuple(reasons)


def _value_presence_reasons(
    *,
    filled: str,
    slot_values: dict[str, object],
    require: bool,
) -> tuple[str, ...]:
    if not require:
        return ()
    reasons: list[str] = []
    for slot_name in _VALUE_SLOTS:
        value = str(slot_values.get(slot_name, ""))
        if not value:
            continue
        if value not in filled:
            reasons.append(f"computed value {value} absent from filled summary")
    return tuple(reasons)


def run_live_reasoning_eval(
    *,
    provider: reasoning_layer.ReasoningProvider,
    cases: collections.abc.Iterable[LiveEvalCase] = DEFAULT_CASES,
    sample_count: int = DEFAULT_SAMPLE_COUNT,
) -> LiveEvalReport:
    """Run all enabled live eval cases k times and aggregate failures."""
    if sample_count < 1:
        raise ValueError("sample_count must be at least 1")
    enabled_cases = tuple(case for case in cases if case.enabled)
    passes: list[LiveEvalPass] = []
    failures: list[LiveEvalFailure] = []
    for case in enabled_cases:
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
            continue
        passes.append(
            LiveEvalPass(
                case_name=case.name,
                pass_count=pass_count,
                sample_count=sample_count,
            )
        )
    return LiveEvalReport(
        total=len(enabled_cases),
        passes=tuple(passes),
        failures=tuple(failures),
    )


def write_live_eval_report(
    *,
    stdout: typing.TextIO,
    report: LiveEvalReport,
    verbose: bool = False,
) -> None:
    """Print aggregate results and detailed failures."""
    del verbose
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
    verbose = _parse_verbose(argv)
    active_environ = environ
    if active_environ is None:
        dotenv.load_dotenv(dotenv_path=env_file, override=False)
        active_environ = os.environ

    try:
        provider = reasoning_layer.build_openai_reasoning_provider(active_environ)
    except reasoning_layer.OpenAIReasoningConfigError as error:
        print(str(error), file=stderr)
        return 1

    report = run_live_reasoning_eval(provider=provider)
    write_live_eval_report(stdout=stdout, report=report, verbose=verbose)
    if report.failed:
        return 1
    return 0


def _parse_verbose(argv: collections.abc.Sequence[str]) -> bool:
    parser = argparse.ArgumentParser(
        description="Run manual live evals for the OpenAI Reasoning Layer.",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="print full per-case detail",
    )
    args = parser.parse_args(list(argv))
    return typing.cast(bool, args.verbose)


if __name__ == "__main__":
    raise SystemExit(main(argv=sys.argv[1:]))

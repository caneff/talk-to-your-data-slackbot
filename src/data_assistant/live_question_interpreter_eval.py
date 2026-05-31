"""Manual live eval suite for the OpenAI-backed Question Interpreter."""

from __future__ import annotations

import argparse
import collections.abc
import dataclasses
import datetime
import os
import pathlib
import sys
import textwrap
import typing

import dotenv

import data_assistant.question_interpreter as question_interpreter
import data_assistant.question_interpreter_test_support as test_support
import data_assistant.semantic_layer.schema as schema
import data_assistant.semantic_layer.testing_support as semantic_layer_testing

ProviderResult: typing.TypeAlias = (
    question_interpreter.QuestionFrameProposal
    | question_interpreter.ProviderFailure
)


@dataclasses.dataclass(frozen=True)
class LiveEvalCase:
    """One manual live eval prompt with expected Question Frame meaning."""

    name: str
    question: str
    expected: question_interpreter.QuestionFrameProposal
    enabled: bool = True


@dataclasses.dataclass(frozen=True)
class LiveEvalFailure:
    """One failed live eval case."""

    case_name: str
    question: str
    expected: question_interpreter.QuestionFrameProposal
    actual: ProviderResult
    reasons: tuple[str, ...]


@dataclasses.dataclass(frozen=True)
class LiveEvalPass:
    """One passed live eval case."""

    case_name: str
    question: str
    expected: question_interpreter.QuestionFrameProposal
    actual: question_interpreter.QuestionFrameProposal


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


DEFAULT_CASES: tuple[LiveEvalCase, ...] = (
    LiveEvalCase(
        name="canonical_question",
        question="What was total revenue by region in January 2026?",
        expected=test_support.question_frame_proposal(),
    ),
    LiveEvalCase(
        name="show_total_revenue_by_region",
        question="Show total revenue by region in January 2026.",
        expected=test_support.question_frame_proposal(),
    ),
    LiveEvalCase(
        name="summarize_total_revenue_by_region",
        question="Summarize total revenue by region for January 2026.",
        expected=test_support.question_frame_proposal(),
    ),
)


def compare_question_frame_meaning(
    *,
    expected: question_interpreter.QuestionFrameProposal,
    actual: question_interpreter.QuestionFrameProposal,
) -> tuple[str, ...]:
    """Return field-level mismatches for proposal meaning."""
    mismatches: list[str] = []
    _append_scalar_mismatch(
        mismatches=mismatches,
        field="intent",
        expected=expected.intent,
        actual=actual.intent,
    )
    _append_scalar_mismatch(
        mismatches=mismatches,
        field="metric",
        expected=expected.metric,
        actual=actual.metric,
    )
    _append_scalar_mismatch(
        mismatches=mismatches,
        field="field_operations",
        expected=expected.field_operations,
        actual=actual.field_operations,
    )
    return tuple(mismatches)


def run_live_question_interpreter_eval(
    *,
    provider: question_interpreter.QuestionInterpreterProvider,
    semantic_layer: schema.SemanticLayer,
    cases: collections.abc.Iterable[LiveEvalCase] = DEFAULT_CASES,
) -> LiveEvalReport:
    """Run all enabled live eval cases and aggregate failures."""
    semantic_layer_context = question_interpreter.build_semantic_layer_context(
        semantic_layer
    )
    enabled_cases = tuple(case for case in cases if case.enabled)
    passes: list[LiveEvalPass] = []
    failures: list[LiveEvalFailure] = []
    for case in enabled_cases:
        actual = provider.propose_question_frame(
            question=case.question,
            semantic_layer_context=semantic_layer_context,
        )
        if isinstance(actual, question_interpreter.ProviderFailure):
            failures.append(
                LiveEvalFailure(
                    case_name=case.name,
                    question=case.question,
                    expected=case.expected,
                    actual=actual,
                    reasons=_case_failure_reasons(
                        expected=case.expected,
                        actual=actual,
                    ),
                )
            )
            continue

        reasons = compare_question_frame_meaning(expected=case.expected, actual=actual)
        if reasons:
            failures.append(
                LiveEvalFailure(
                    case_name=case.name,
                    question=case.question,
                    expected=case.expected,
                    actual=actual,
                    reasons=reasons,
                )
            )
            continue
        passes.append(
            LiveEvalPass(
                case_name=case.name,
                question=case.question,
                expected=case.expected,
                actual=actual,
            )
        )
    return LiveEvalReport(
        total=len(enabled_cases),
        passes=tuple(passes),
        failures=tuple(failures),
    )


def _case_failure_reasons(
    *,
    expected: question_interpreter.QuestionFrameProposal,
    actual: ProviderResult,
) -> tuple[str, ...]:
    if isinstance(actual, question_interpreter.ProviderFailure):
        return (f"provider failure: {actual.reason}",)
    return compare_question_frame_meaning(expected=expected, actual=actual)


def write_live_eval_report(
    *,
    stdout: typing.TextIO,
    report: LiveEvalReport,
    verbose: bool = False,
) -> None:
    """Print aggregate results and detailed failures."""
    stdout.write(f"Total cases: {report.total}\n")
    stdout.write(f"Passed: {report.passed}\n")
    stdout.write(f"Failed: {report.failed}\n")
    if verbose:
        for passed_case in report.passes:
            stdout.write(_passed_case_report(passed_case))
    for failure in report.failures:
        stdout.write(_failure_report(failure))


def _passed_case_report(passed_case: LiveEvalPass) -> str:
    return textwrap.dedent(f"""
        [PASS] {passed_case.case_name}
        Question: {passed_case.question}
        Expected: {_proposal_debug_string(passed_case.expected)}
        Actual: {_proposal_debug_string(passed_case.actual)}
        """)


def _failure_report(failure: LiveEvalFailure) -> str:
    reasons = "".join(f"Reason: {reason}\n" for reason in failure.reasons)
    return (
        textwrap.dedent(f"""
            [FAIL] {failure.case_name}
            Question: {failure.question}
            Expected: {_proposal_debug_string(failure.expected)}
            Actual: {_provider_result_debug_string(failure.actual)}
            """)
        + reasons
    )


def main(
    *,
    stdout: typing.TextIO = sys.stdout,
    stderr: typing.TextIO = sys.stderr,
    environ: collections.abc.Mapping[str, str] | None = None,
    env_file: str | pathlib.Path = ".env",
    argv: collections.abc.Sequence[str] = (),
) -> int:
    """Run manual live eval suite against real OpenAI provider config."""
    verbose = _parse_verbose(argv)
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

    report = run_live_question_interpreter_eval(
        provider=provider,
        semantic_layer=semantic_layer_testing.semantic_layer_with_table(),
    )
    write_live_eval_report(stdout=stdout, report=report, verbose=verbose)
    if report.failed:
        return 1
    return 0


def _parse_verbose(argv: collections.abc.Sequence[str]) -> bool:
    parser = argparse.ArgumentParser(
        description="Run manual live evals for OpenAI Question Interpreter output.",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="print full expected and actual details for passed cases",
    )
    args = parser.parse_args(list(argv))
    return typing.cast(bool, args.verbose)


def _load_env_file(
    path: str | pathlib.Path = ".env",
) -> None:
    """Load local dotenv values without overriding exported environment vars."""
    dotenv.load_dotenv(dotenv_path=path, override=False)


def _append_scalar_mismatch(
    *,
    mismatches: list[str],
    field: str,
    expected: object,
    actual: object,
) -> None:
    if expected != actual:
        mismatches.append(
            f"{field}: expected {_debug_value(expected)}, got {_debug_value(actual)}"
        )


def _debug_value(value: object) -> str:
    if isinstance(value, datetime.date):
        return value.isoformat()
    return repr(value)


def _proposal_debug_string(
    proposal: question_interpreter.QuestionFrameProposal,
) -> str:
    return proposal.model_dump_json()


def _provider_result_debug_string(
    result: ProviderResult,
) -> str:
    if isinstance(result, question_interpreter.ProviderFailure):
        return f"ProviderFailure(reason={result.reason!r})"
    return _proposal_debug_string(result)


if __name__ == "__main__":
    raise SystemExit(main(argv=sys.argv[1:]))

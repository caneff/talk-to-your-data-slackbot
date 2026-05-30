"""Manual live eval suite for the OpenAI-backed Question Interpreter."""

from __future__ import annotations

import collections.abc
import dataclasses
import datetime
import os
import sys
import typing

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
class LiveEvalReport:
    """Aggregate live eval results."""

    total: int
    passed: int
    failures: tuple[LiveEvalFailure, ...]

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
        field="dimension",
        expected=expected.dimension,
        actual=actual.dimension,
    )
    _append_scalar_mismatch(
        mismatches=mismatches,
        field="filters",
        expected=expected.filters,
        actual=actual.filters,
    )
    expected_time_range = expected.time_range
    actual_time_range = actual.time_range
    if expected_time_range is None or actual_time_range is None:
        _append_scalar_mismatch(
            mismatches=mismatches,
            field="time_range",
            expected=expected_time_range,
            actual=actual_time_range,
        )
        return tuple(mismatches)

    _append_scalar_mismatch(
        mismatches=mismatches,
        field="time_range.start_date",
        expected=expected_time_range.start_date,
        actual=actual_time_range.start_date,
    )
    _append_scalar_mismatch(
        mismatches=mismatches,
        field="time_range.end_date",
        expected=expected_time_range.end_date,
        actual=actual_time_range.end_date,
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
    failures: list[LiveEvalFailure] = []
    passed = 0
    for case in enabled_cases:
        actual = provider.propose_question_frame(
            question=case.question,
            semantic_layer_context=semantic_layer_context,
        )
        reasons = _case_failure_reasons(expected=case.expected, actual=actual)
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
        passed += 1
    return LiveEvalReport(
        total=len(enabled_cases),
        passed=passed,
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
) -> None:
    """Print aggregate results and detailed failures."""
    stdout.write(f"Total cases: {report.total}\n")
    stdout.write(f"Passed: {report.passed}\n")
    stdout.write(f"Failed: {report.failed}\n")
    for failure in report.failures:
        stdout.write("\n")
        stdout.write(f"[FAIL] {failure.case_name}\n")
        stdout.write(f"Question: {failure.question}\n")
        stdout.write(f"Expected: {_proposal_debug_string(failure.expected)}\n")
        stdout.write(f"Actual: {_provider_result_debug_string(failure.actual)}\n")
        for reason in failure.reasons:
            stdout.write(f"Reason: {reason}\n")


def main(
    *,
    stdout: typing.TextIO = sys.stdout,
    stderr: typing.TextIO = sys.stderr,
    environ: collections.abc.Mapping[str, str] = os.environ,
) -> int:
    """Run manual live eval suite against real OpenAI provider config."""
    try:
        provider = question_interpreter.build_openai_question_interpreter_provider(
            environ
        )
    except question_interpreter.OpenAIQuestionInterpreterConfigError as error:
        print(str(error), file=stderr)
        return 1

    report = run_live_question_interpreter_eval(
        provider=provider,
        semantic_layer=semantic_layer_testing.semantic_layer_with_table(),
    )
    write_live_eval_report(stdout=stdout, report=report)
    if report.failed:
        return 1
    return 0


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
    raise SystemExit(main())

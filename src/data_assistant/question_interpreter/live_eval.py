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
import tqdm

import data_assistant.question_interpreter as question_interpreter
import data_assistant.question_interpreter.question_frame_cases as question_frame_cases
import data_assistant.semantic_layer.catalog as semantic_layer_catalog
import data_assistant.semantic_layer.loader as semantic_layer_loader

ProviderResult: typing.TypeAlias = (
    question_interpreter.QuestionFrameProposal | question_interpreter.ProviderFailure
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
    pass_count: int = 0
    sample_count: int = 1


@dataclasses.dataclass(frozen=True)
class LiveEvalPass:
    """One passed live eval case."""

    case_name: str
    question: str
    expected: question_interpreter.QuestionFrameProposal
    actual: question_interpreter.QuestionFrameProposal
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
        question=case.question,
        expected=case.expected,
        enabled=case.enabled,
    )
    for case in question_frame_cases.SHARED_QUESTION_FRAME_CASES
)
DEFAULT_SAMPLE_COUNT = 3


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
        field="metric_ambiguity",
        expected=expected.metric_ambiguity,
        actual=actual.metric_ambiguity,
    )
    _append_scalar_mismatch(
        mismatches=mismatches,
        field="all_time",
        expected=expected.all_time,
        actual=actual.all_time,
    )
    _append_field_operations_mismatches(
        mismatches=mismatches,
        expected=expected.field_operations,
        actual=actual.field_operations,
    )
    return tuple(mismatches)


def run_live_question_interpreter_eval(
    *,
    provider: question_interpreter.QuestionInterpreterProvider,
    semantic_layer: semantic_layer_catalog.SemanticLayerCatalog,
    cases: collections.abc.Iterable[LiveEvalCase] = DEFAULT_CASES,
    sample_count: int = DEFAULT_SAMPLE_COUNT,
    progress: bool = False,
    progress_file: typing.TextIO | None = None,
) -> LiveEvalReport:
    """Run all enabled live eval cases and aggregate failures."""
    if sample_count < 1:
        raise ValueError("sample_count must be at least 1")
    semantic_layer_context = question_interpreter.build_semantic_layer_context(
        semantic_layer
    )
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
            pass_count = 0
            sample_failures: list[str] = []
            last_actual: ProviderResult | None = None
            last_failure_actual: ProviderResult | None = None
            for sample_index in range(sample_count):
                actual = provider.propose_question_frame(
                    question=case.question,
                    semantic_layer_context=semantic_layer_context,
                )
                last_actual = actual
                reasons = _case_failure_reasons(
                    expected=case.expected,
                    actual=actual,
                )
                if reasons:
                    last_failure_actual = actual
                    sample_failures.extend(
                        f"sample {sample_index + 1}: {reason}" for reason in reasons
                    )
                    continue
                pass_count += 1

            if last_actual is None:
                raise AssertionError("live eval must record at least one sample result")
            if sample_failures:
                failures.append(
                    LiveEvalFailure(
                        case_name=case.name,
                        question=case.question,
                        expected=case.expected,
                        actual=typing.cast(ProviderResult, last_failure_actual),
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
                    question=case.question,
                    expected=case.expected,
                    actual=typing.cast(
                        question_interpreter.QuestionFrameProposal,
                        last_actual,
                    ),
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
    for passed_case in report.passes:
        stdout.write(_passed_case_summary_line(passed_case))
        if verbose:
            stdout.write(_passed_case_report(passed_case))
    for failure in report.failures:
        stdout.write(_failure_report(failure))


def _passed_case_summary_line(passed_case: LiveEvalPass) -> str:
    return (
        f"[PASS] {passed_case.case_name} "
        f"(pass rate: {passed_case.pass_count}/{passed_case.sample_count})\n"
    )


def _passed_case_report(passed_case: LiveEvalPass) -> str:
    return textwrap.dedent(f"""
        Question: {passed_case.question}
        Expected: {_proposal_debug_string(passed_case.expected)}
        Actual: {_proposal_debug_string(passed_case.actual)}
        """)


def _failure_report(failure: LiveEvalFailure) -> str:
    reasons = "".join(f"Reason: {reason}\n" for reason in failure.reasons)
    pass_rate = f"{failure.pass_count}/{failure.sample_count}"
    return (
        textwrap.dedent(f"""
            [FAIL] {failure.case_name} (pass rate: {pass_rate})
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

    report = run_live_question_interpreter_eval(
        provider=provider,
        semantic_layer=semantic_layer_loader.load_semantic_layer(),
        progress=args.progress,
        progress_file=stderr,
    )
    write_live_eval_report(stdout=stdout, report=report, verbose=args.verbose)
    if report.failed:
        return 1
    return 0


@dataclasses.dataclass(frozen=True)
class _CliArgs:
    verbose: bool
    progress: bool


def _parse_args(argv: collections.abc.Sequence[str]) -> _CliArgs:
    parser = argparse.ArgumentParser(
        description="Run manual live evals for OpenAI Question Interpreter output.",
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
    args = parser.parse_args(list(argv))
    return _CliArgs(
        verbose=typing.cast(bool, args.verbose),
        progress=not typing.cast(bool, args.no_progress),
    )


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


def _load_env_file(
    path: str | pathlib.Path = ".env",
) -> None:
    """Load local dotenv values without overriding exported environment vars."""
    dotenv.load_dotenv(dotenv_path=path, override=False)


_FIELD_OPERATION_ATTRIBUTES: tuple[str, ...] = (
    "operation",
    "field",
    "lower",
    "upper",
    "values",
)


def _append_field_operations_mismatches(
    *,
    mismatches: list[str],
    expected: tuple[question_interpreter.FieldOperationProposal, ...],
    actual: tuple[question_interpreter.FieldOperationProposal, ...],
) -> None:
    """Report only the field operations (and attributes) that actually differ."""
    common = min(len(expected), len(actual))
    for index in range(common):
        _append_field_operation_mismatch(
            mismatches=mismatches,
            index=index,
            expected=expected[index],
            actual=actual[index],
        )
    for index in range(common, len(expected)):
        mismatches.append(
            f"field_operations[{index}]: "
            f"expected {_field_operation_debug_string(expected[index])}, "
            "got (missing)"
        )
    for index in range(common, len(actual)):
        mismatches.append(
            f"field_operations[{index}]: expected (missing), "
            f"got {_field_operation_debug_string(actual[index])}"
        )


def _append_field_operation_mismatch(
    *,
    mismatches: list[str],
    index: int,
    expected: question_interpreter.FieldOperationProposal,
    actual: question_interpreter.FieldOperationProposal,
) -> None:
    for attribute in _FIELD_OPERATION_ATTRIBUTES:
        _append_scalar_mismatch(
            mismatches=mismatches,
            field=f"field_operations[{index}].{attribute}",
            expected=getattr(expected, attribute),
            actual=getattr(actual, attribute),
        )


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


def _field_operation_debug_string(
    operation: question_interpreter.FieldOperationProposal,
) -> str:
    return operation.model_dump_json()


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

"""Provider Proposal Eval harness with injected provider dependencies."""

from __future__ import annotations

import collections.abc
import concurrent.futures
import dataclasses
import datetime
import json
import pathlib
import textwrap
import typing

import tqdm

import data_assistant.question_interpreter as question_interpreter
import data_assistant.question_interpreter.provider_proposal_cases as proposal_cases
import data_assistant.semantic_layer.catalog as semantic_layer_catalog

ProviderResult: typing.TypeAlias = (
    question_interpreter.ProviderProposal | question_interpreter.ProviderFailure
)


@dataclasses.dataclass(frozen=True)
class ProviderProposalEvalCase:
    """One provider proposal eval prompt with expected proposal meaning."""

    name: str
    question: str
    expected: question_interpreter.ProviderProposal
    enabled: bool = True
    deferred: bool = False


@dataclasses.dataclass(frozen=True)
class ProviderProposalEvalFailure:
    """One failed provider proposal eval case."""

    case_name: str
    question: str
    expected: question_interpreter.ProviderProposal
    actual: ProviderResult
    reasons: tuple[str, ...]
    pass_count: int = 0
    sample_count: int = 1


@dataclasses.dataclass(frozen=True)
class ProviderProposalEvalPass:
    """One passed provider proposal eval case."""

    case_name: str
    question: str
    expected: question_interpreter.ProviderProposal
    actual: question_interpreter.ProviderProposal
    pass_count: int = 1
    sample_count: int = 1


@dataclasses.dataclass(frozen=True)
class ProviderProposalEvalReport:
    """Aggregate provider proposal eval results."""

    total: int
    passes: tuple[ProviderProposalEvalPass, ...]
    failures: tuple[ProviderProposalEvalFailure, ...]
    known_deferred: tuple[ProviderProposalEvalFailure, ...] = ()
    tripwires: tuple[ProviderProposalEvalPass, ...] = ()

    @property
    def passed(self) -> int:
        return len(self.passes)

    @property
    def failed(self) -> int:
        return len(self.failures)


@dataclasses.dataclass(frozen=True)
class _CaseEvaluation:
    case_number: int
    case: ProviderProposalEvalCase
    actual: ProviderResult
    failure_actual: ProviderResult | None
    pass_count: int
    sample_failures: tuple[str, ...]


@dataclasses.dataclass(frozen=True)
class _CaseProgress:
    status: typing.Any
    progress: typing.Any


DEFAULT_CASES: tuple[ProviderProposalEvalCase, ...] = tuple(
    ProviderProposalEvalCase(
        name=case.name,
        question=case.question,
        expected=case.expected,
        enabled=case.enabled,
        deferred=case.deferred,
    )
    for case in proposal_cases.SHARED_PROVIDER_PROPOSAL_CASES
)
DEFAULT_SAMPLE_COUNT = 3
DEFAULT_FAILURES_DIR = pathlib.Path("eval_results")


def compare_provider_proposal_meaning(
    *,
    expected: question_interpreter.ProviderProposal,
    actual: question_interpreter.ProviderProposal,
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
        field="unknown_metric",
        expected=expected.unknown_metric,
        actual=actual.unknown_metric,
    )
    _append_scalar_mismatch(
        mismatches=mismatches,
        field="limit",
        expected=expected.limit,
        actual=actual.limit,
    )
    _append_scalar_mismatch(
        mismatches=mismatches,
        field="sort_direction",
        expected=expected.sort_direction,
        actual=actual.sort_direction,
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


def select_cases(
    enabled: collections.abc.Sequence[ProviderProposalEvalCase],
    *,
    start_at: int = 1,
    stop_at: int | None = None,
    only_cases: tuple[str, ...] | None = None,
) -> tuple[tuple[int, ProviderProposalEvalCase], ...]:
    """Resolve selected cases as ``(absolute_1_based_index, case)`` pairs."""
    indexed = tuple(enumerate(enabled, start=1))
    if only_cases is not None:
        if start_at != 1 or stop_at is not None:
            raise ValueError(
                "--only-cases cannot be combined with --start-at or --stop-at"
            )
        return _select_only_cases(indexed, only_cases)
    total = len(enabled)
    stop = total if stop_at is None else stop_at
    if not (1 <= start_at <= stop <= total):
        raise ValueError(
            f"invalid case range: require 1 <= start ({start_at}) <= "
            f"stop ({stop}) <= enabled count ({total})"
        )
    return indexed[start_at - 1 : stop]


def _select_only_cases(
    indexed: tuple[tuple[int, ProviderProposalEvalCase], ...],
    only_cases: tuple[str, ...],
) -> tuple[tuple[int, ProviderProposalEvalCase], ...]:
    by_name = {case.name: index for index, case in indexed}
    total = len(indexed)
    chosen: set[int] = set()
    for token in only_cases:
        if token.isdigit():
            index = int(token)
            if not (1 <= index <= total):
                raise ValueError(
                    f"--only-cases index out of range: {token} (enabled count {total})"
                )
            chosen.add(index)
            continue
        if token not in by_name:
            raise ValueError(f"--only-cases unknown case name: {token}")
        chosen.add(by_name[token])
    return tuple(pair for pair in indexed if pair[0] in chosen)


def run_provider_proposal_eval(
    *,
    provider: question_interpreter.QuestionInterpreterProvider,
    semantic_layer: semantic_layer_catalog.SemanticLayerCatalog,
    cases: collections.abc.Iterable[ProviderProposalEvalCase] = DEFAULT_CASES,
    sample_count: int = DEFAULT_SAMPLE_COUNT,
    progress: bool = False,
    progress_file: typing.TextIO | None = None,
    failures_file: typing.TextIO | None = None,
    start_at: int = 1,
    stop_at: int | None = None,
    only_cases: tuple[str, ...] | None = None,
    concurrency: int = 1,
) -> ProviderProposalEvalReport:
    """Run selected enabled provider proposal eval cases."""
    if sample_count < 1:
        raise ValueError("sample_count must be at least 1")
    if concurrency < 1:
        raise ValueError("concurrency must be at least 1")
    semantic_layer_context = question_interpreter.build_semantic_layer_context(
        semantic_layer
    )
    enabled_cases = tuple(case for case in cases if case.enabled)
    selected = select_cases(
        enabled_cases,
        start_at=start_at,
        stop_at=stop_at,
        only_cases=only_cases,
    )
    passes: list[ProviderProposalEvalPass] = []
    failures: list[ProviderProposalEvalFailure] = []
    known_deferred: list[ProviderProposalEvalFailure] = []
    tripwires: list[ProviderProposalEvalPass] = []
    evaluations = _run_case_evaluations(
        provider=provider,
        semantic_layer_context=semantic_layer_context,
        selected=selected,
        sample_count=sample_count,
        concurrency=concurrency,
        progress=progress,
        progress_file=progress_file,
    )
    for evaluation in evaluations:
        _record_case_evaluation(
            evaluation=evaluation,
            sample_count=sample_count,
            failures_file=failures_file,
            passes=passes,
            failures=failures,
            known_deferred=known_deferred,
            tripwires=tripwires,
        )
    return ProviderProposalEvalReport(
        total=len(selected),
        passes=tuple(passes),
        failures=tuple(failures),
        known_deferred=tuple(known_deferred),
        tripwires=tuple(tripwires),
    )


def _run_case_evaluations(
    *,
    provider: question_interpreter.QuestionInterpreterProvider,
    semantic_layer_context: dict[str, object],
    selected: tuple[tuple[int, ProviderProposalEvalCase], ...],
    sample_count: int,
    concurrency: int,
    progress: bool,
    progress_file: typing.TextIO | None,
) -> tuple[_CaseEvaluation, ...]:
    progress_bar = _new_case_progress(
        enabled=progress,
        total=len(selected),
        progress_file=progress_file,
    )
    try:
        if concurrency == 1:
            evaluations: list[_CaseEvaluation] = []
            for selection_index, (case_number, case) in enumerate(selected, start=1):
                _write_case_progress_line(
                    progress_bar=progress_bar,
                    prefix="Provider Proposal Eval current",
                    case_index=selection_index,
                    total=len(selected),
                    case_name=case.name,
                )
                evaluations.append(
                    _evaluate_case(
                        provider=provider,
                        semantic_layer_context=semantic_layer_context,
                        case_number=case_number,
                        case=case,
                        sample_count=sample_count,
                    )
                )
                _update_case_progress(progress_bar)
            return tuple(evaluations)
        return _run_case_evaluations_concurrently(
            provider=provider,
            semantic_layer_context=semantic_layer_context,
            selected=selected,
            sample_count=sample_count,
            concurrency=concurrency,
            progress_bar=progress_bar,
        )
    finally:
        if progress_bar is not None:
            _close_case_progress(progress_bar)


def _run_case_evaluations_concurrently(
    *,
    provider: question_interpreter.QuestionInterpreterProvider,
    semantic_layer_context: dict[str, object],
    selected: tuple[tuple[int, ProviderProposalEvalCase], ...],
    sample_count: int,
    concurrency: int,
    progress_bar: _CaseProgress | None,
) -> tuple[_CaseEvaluation, ...]:
    max_workers = min(concurrency, len(selected))
    if max_workers == 0:
        return ()
    by_selection_index: dict[int, _CaseEvaluation] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(
                _evaluate_case,
                provider=provider,
                semantic_layer_context=semantic_layer_context,
                case_number=case_number,
                case=case,
                sample_count=sample_count,
            ): selection_index
            for selection_index, (case_number, case) in enumerate(selected, start=1)
        }
        for completed_count, future in enumerate(
            concurrent.futures.as_completed(futures),
            start=1,
        ):
            evaluation = future.result()
            by_selection_index[futures[future]] = evaluation
            _write_case_progress_line(
                progress_bar=progress_bar,
                prefix="Provider Proposal Eval completed",
                case_index=completed_count,
                total=len(selected),
                case_name=evaluation.case.name,
            )
            _update_case_progress(progress_bar)
    return tuple(
        by_selection_index[selection_index]
        for selection_index in range(1, len(selected) + 1)
    )


def _evaluate_case(
    *,
    provider: question_interpreter.QuestionInterpreterProvider,
    semantic_layer_context: dict[str, object],
    case_number: int,
    case: ProviderProposalEvalCase,
    sample_count: int,
) -> _CaseEvaluation:
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
        reasons = _case_failure_reasons(expected=case.expected, actual=actual)
        if reasons:
            last_failure_actual = actual
            sample_failures.extend(
                f"sample {sample_index + 1}: {reason}" for reason in reasons
            )
            continue
        pass_count += 1

    if last_actual is None:
        raise AssertionError(
            "provider proposal eval must record at least one sample result"
        )
    return _CaseEvaluation(
        case_number=case_number,
        case=case,
        actual=last_actual,
        failure_actual=last_failure_actual,
        pass_count=pass_count,
        sample_failures=tuple(sample_failures),
    )


def _record_case_evaluation(
    *,
    evaluation: _CaseEvaluation,
    sample_count: int,
    failures_file: typing.TextIO | None,
    passes: list[ProviderProposalEvalPass],
    failures: list[ProviderProposalEvalFailure],
    known_deferred: list[ProviderProposalEvalFailure],
    tripwires: list[ProviderProposalEvalPass],
) -> None:
    case = evaluation.case
    if evaluation.sample_failures:
        if evaluation.failure_actual is None:
            raise AssertionError("failed eval case must record a failed sample result")
        failure = ProviderProposalEvalFailure(
            case_name=case.name,
            question=case.question,
            expected=case.expected,
            actual=evaluation.failure_actual,
            reasons=evaluation.sample_failures,
            pass_count=evaluation.pass_count,
            sample_count=sample_count,
        )
        if case.deferred:
            known_deferred.append(failure)
            return
        failures.append(failure)
        _write_failure_line(
            failures_file=failures_file,
            case_number=evaluation.case_number,
            failure=failure,
        )
        return
    passed_case = ProviderProposalEvalPass(
        case_name=case.name,
        question=case.question,
        expected=case.expected,
        actual=typing.cast(
            question_interpreter.ProviderProposal,
            evaluation.actual,
        ),
        pass_count=evaluation.pass_count,
        sample_count=sample_count,
    )
    if case.deferred:
        tripwires.append(passed_case)
    else:
        passes.append(passed_case)


def _case_failure_reasons(
    *,
    expected: question_interpreter.ProviderProposal,
    actual: ProviderResult,
) -> tuple[str, ...]:
    if isinstance(actual, question_interpreter.ProviderFailure):
        return (f"provider failure: {actual.reason}",)
    return compare_provider_proposal_meaning(expected=expected, actual=actual)


def _write_failure_line(
    *,
    failures_file: typing.TextIO | None,
    case_number: int,
    failure: ProviderProposalEvalFailure,
) -> None:
    if failures_file is None:
        return
    record = {
        "case_number": case_number,
        "case_name": failure.case_name,
        "question": failure.question,
        "pass_count": failure.pass_count,
        "sample_count": failure.sample_count,
        "reasons": list(failure.reasons),
        "expected": failure.expected.model_dump(),
        "actual": _failure_actual_payload(failure.actual),
    }
    failures_file.write(json.dumps(record) + "\n")
    failures_file.flush()


def _failure_actual_payload(actual: ProviderResult) -> dict[str, typing.Any]:
    if isinstance(actual, question_interpreter.ProviderFailure):
        return {"provider_failure": actual.reason}
    return actual.model_dump()


def write_provider_proposal_eval_report(
    *,
    stdout: typing.TextIO,
    report: ProviderProposalEvalReport,
    verbose: bool = False,
) -> None:
    """Print aggregate results and detailed failures."""
    stdout.write(f"Total cases: {report.total}\n")
    stdout.write(f"Passed: {report.passed}\n")
    stdout.write(f"Failed: {report.failed}\n")
    stdout.write(
        f"Known-deferred: {len(report.known_deferred)} (expected not-yet-supported)\n"
    )
    for deferred_case in report.known_deferred:
        stdout.write(
            f"[KNOWN-DEFERRED] {deferred_case.case_name} "
            f"(pass rate: {deferred_case.pass_count}/{deferred_case.sample_count})\n"
        )
    for tripwire in report.tripwires:
        stdout.write(
            f"[TRIPWIRE] {tripwire.case_name} now passes — remove deferred=True\n"
        )
    for passed_case in report.passes:
        stdout.write(_passed_case_summary_line(passed_case))
        if verbose:
            stdout.write(_passed_case_report(passed_case))
    for failure in report.failures:
        stdout.write(_failure_report(failure))


def _passed_case_summary_line(passed_case: ProviderProposalEvalPass) -> str:
    return (
        f"[PASS] {passed_case.case_name} "
        f"(pass rate: {passed_case.pass_count}/{passed_case.sample_count})\n"
    )


def _passed_case_report(passed_case: ProviderProposalEvalPass) -> str:
    return textwrap.dedent(f"""
        Question: {passed_case.question}
        Expected: {_proposal_debug_string(passed_case.expected)}
        Actual: {_proposal_debug_string(passed_case.actual)}
        """)


def _failure_report(failure: ProviderProposalEvalFailure) -> str:
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


def resolve_default_failures_path() -> pathlib.Path:
    timestamp = datetime.datetime.now(datetime.UTC).strftime("%Y%m%dT%H%M%SZ")
    return DEFAULT_FAILURES_DIR / f"provider_proposal_eval_failures_{timestamp}.jsonl"


def _new_case_progress(
    *,
    enabled: bool,
    total: int,
    progress_file: typing.TextIO | None,
) -> _CaseProgress | None:
    if not enabled:
        return None
    status = tqdm.tqdm(
        total=0,
        file=progress_file,
        leave=False,
        dynamic_ncols=True,
        bar_format="{desc}",
        position=0,
    )
    progress = tqdm.tqdm(
        total=total,
        desc="Provider Proposal Eval",
        file=progress_file,
        leave=False,
        dynamic_ncols=True,
        bar_format="{desc} |{bar}| {n_fmt}/{total_fmt} {percentage:3.0f}%",
        position=1,
    )
    return _CaseProgress(status=status, progress=progress)


def _close_case_progress(progress_bar: _CaseProgress) -> None:
    progress_bar.progress.close()
    progress_bar.status.close()


def _write_case_progress_line(
    *,
    progress_bar: _CaseProgress | None,
    prefix: str,
    case_index: int,
    total: int,
    case_name: str,
) -> None:
    if progress_bar is None:
        return
    progress_bar.status.set_description_str(
        f"{prefix} {case_index}/{total}: {case_name}",
        refresh=True,
    )


def _update_case_progress(progress_bar: _CaseProgress | None) -> None:
    if progress_bar is None:
        return
    progress_bar.progress.update(1)


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
    expected: tuple[question_interpreter.ProviderFieldOperation, ...],
    actual: tuple[question_interpreter.ProviderFieldOperation, ...],
) -> None:
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
    expected: question_interpreter.ProviderFieldOperation,
    actual: question_interpreter.ProviderFieldOperation,
) -> None:
    for attribute in _FIELD_OPERATION_ATTRIBUTES:
        field = f"field_operations[{index}].{attribute}"
        expected_value = getattr(expected, attribute)
        actual_value = getattr(actual, attribute)
        if attribute == "values":
            if not _values_equal(expected_value, actual_value):
                mismatches.append(
                    f"{field}: expected {_debug_value(expected_value)}, "
                    f"got {_debug_value(actual_value)}"
                )
            continue
        _append_scalar_mismatch(
            mismatches=mismatches,
            field=field,
            expected=expected_value,
            actual=actual_value,
        )


def _values_equal(
    expected: tuple[object, ...],
    actual: tuple[object, ...],
) -> bool:
    if len(expected) != len(actual):
        return False
    return all(
        _norm_value(expected_value) == _norm_value(actual_value)
        for expected_value, actual_value in zip(expected, actual, strict=True)
    )


def _norm_value(value: object) -> object:
    if isinstance(value, str):
        return value.casefold()
    return value


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
    return repr(value)


def _field_operation_debug_string(
    operation: question_interpreter.ProviderFieldOperation,
) -> str:
    return operation.model_dump_json()


def _proposal_debug_string(
    proposal: question_interpreter.ProviderProposal,
) -> str:
    return proposal.model_dump_json()


def _provider_result_debug_string(result: ProviderResult) -> str:
    if isinstance(result, question_interpreter.ProviderFailure):
        return f"ProviderFailure(reason={result.reason!r})"
    return _proposal_debug_string(result)

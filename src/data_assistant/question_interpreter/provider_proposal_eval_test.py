import io
import json
import re
import threading

import pytest

import data_assistant.question_interpreter as question_interpreter
import data_assistant.question_interpreter.provider_proposal_cases as proposal_cases
import data_assistant.question_interpreter.provider_proposal_eval as proposal_eval
import data_assistant.question_interpreter.testing_support as test_support
import data_assistant.semantic_layer.testing_support as semantic_layer_testing


class _SequenceProvider:
    def __init__(self, *results: proposal_eval.ProviderResult) -> None:
        self._results = list(results)
        self.calls: list[tuple[str, dict[str, object]]] = []

    def propose_question_frame(
        self,
        *,
        question: str,
        semantic_layer_context: dict[str, object],
    ) -> proposal_eval.ProviderResult:
        self.calls.append((question, semantic_layer_context))
        if not self._results:
            raise AssertionError("provider called more times than configured")
        return self._results.pop(0)


class _ConcurrentStartProvider:
    def __init__(self, *, expected_call_count: int) -> None:
        self._expected_call_count = expected_call_count
        self._condition = threading.Condition()
        self.calls: list[str] = []

    def propose_question_frame(
        self,
        *,
        question: str,
        semantic_layer_context: dict[str, object],
    ) -> proposal_eval.ProviderResult:
        del semantic_layer_context
        with self._condition:
            self.calls.append(question)
            self._condition.notify_all()
            self._condition.wait_for(
                lambda: len(self.calls) == self._expected_call_count,
                timeout=2,
            )
            if len(self.calls) != self._expected_call_count:
                raise AssertionError("provider calls did not overlap")
        return test_support.question_frame_proposal()


def _eval_case(
    *,
    name: str = "canonical_question",
    expected: question_interpreter.ProviderProposal | None = None,
    deferred: bool = False,
) -> proposal_eval.ProviderProposalEvalCase:
    return proposal_eval.ProviderProposalEvalCase(
        name=name,
        question="What was total revenue by region in January 2026?",
        expected=expected or test_support.question_frame_proposal(),
        deferred=deferred,
    )


def _selection_cases() -> tuple[proposal_eval.ProviderProposalEvalCase, ...]:
    return (
        _eval_case(name="alpha"),
        _eval_case(name="beta"),
        _eval_case(name="gamma"),
    )


def test_default_cases_preserve_catalog_invariants() -> None:
    shared_cases = proposal_cases.SHARED_PROVIDER_PROPOSAL_CASES
    default_cases = proposal_eval.DEFAULT_CASES

    assert len(default_cases) == len(shared_cases)
    assert len({case.name for case in default_cases}) == len(default_cases)
    assert {case.name for case in default_cases} == {case.name for case in shared_cases}
    assert {case.name: (case.enabled, case.deferred) for case in default_cases} == {
        case.name: (case.enabled, case.deferred) for case in shared_cases
    }
    assert all(
        isinstance(case.expected, question_interpreter.ProviderProposal)
        for case in default_cases
    )
    assert all(
        isinstance(field_operation, question_interpreter.ProviderFieldOperation)
        for case in default_cases
        for field_operation in case.expected.field_operations
    )


def test_run_provider_proposal_eval_records_pass_and_respects_sample_count() -> None:
    progress_file = io.StringIO()
    provider = _SequenceProvider(
        test_support.question_frame_proposal(),
        test_support.question_frame_proposal(),
        test_support.question_frame_proposal(),
    )

    report = proposal_eval.run_provider_proposal_eval(
        provider=provider,
        semantic_layer=semantic_layer_testing.semantic_layer_with_table(),
        cases=(_eval_case(),),
        sample_count=3,
        progress=True,
        progress_file=progress_file,
    )

    assert report.total == 1
    assert report.passed == 1
    assert report.failed == 0
    assert report.known_deferred == ()
    assert report.tripwires == ()
    assert report.passes[0].pass_count == 3
    assert report.passes[0].sample_count == 3
    assert [question for question, _ in provider.calls] == [
        "What was total revenue by region in January 2026?",
        "What was total revenue by region in January 2026?",
        "What was total revenue by region in January 2026?",
    ]
    assert "Provider Proposal Eval current 1/1: canonical_question" in (
        progress_file.getvalue()
    )


def test_run_provider_proposal_eval_records_mismatch_failure_and_streams_payloads() -> (
    None
):
    failures_file = io.StringIO()
    provider = _SequenceProvider(
        test_support.question_frame_proposal(metric="gross revenue"),
    )

    report = proposal_eval.run_provider_proposal_eval(
        provider=provider,
        semantic_layer=semantic_layer_testing.semantic_layer_with_table(),
        cases=(_eval_case(),),
        sample_count=1,
        failures_file=failures_file,
    )

    assert report.passed == 0
    assert report.failed == 1
    assert report.failures[0].reasons == (
        "sample 1: metric: expected 'total revenue', got 'gross revenue'",
    )
    assert report.failures[0].actual == test_support.question_frame_proposal(
        metric="gross revenue"
    )

    record = json.loads(failures_file.getvalue())
    assert record["case_number"] == 1
    assert record["case_name"] == "canonical_question"
    assert record["expected"]["metric"] == "total revenue"
    assert record["actual"]["metric"] == "gross revenue"
    assert record["actual"]["field_operations"][0]["operation"] == "group_by"


def test_compare_provider_proposal_meaning_detects_calendar_grouping_mismatch() -> None:
    expected = test_support.question_frame_proposal(
        field_operations=(),
        calendar_grouping=question_interpreter.ProviderCalendarGrouping(
            field="order date",
            grain="month",
        ),
    )
    actual = test_support.question_frame_proposal(field_operations=())

    reasons = proposal_eval.compare_provider_proposal_meaning(
        expected=expected,
        actual=actual,
    )

    assert any(reason.startswith("calendar_grouping:") for reason in reasons)


def test_run_provider_proposal_eval_records_provider_failure_reason_and_payload() -> (
    None
):
    failures_file = io.StringIO()
    provider = _SequenceProvider(question_interpreter.ProviderFailure("timeout"))

    report = proposal_eval.run_provider_proposal_eval(
        provider=provider,
        semantic_layer=semantic_layer_testing.semantic_layer_with_table(),
        cases=(_eval_case(name="provider_failure"),),
        sample_count=1,
        failures_file=failures_file,
    )

    assert report.passed == 0
    assert report.failed == 1
    assert report.failures[0].reasons == ("sample 1: provider failure: timeout",)
    assert report.failures[0].actual == question_interpreter.ProviderFailure("timeout")

    record = json.loads(failures_file.getvalue())
    assert record["actual"] == {"provider_failure": "timeout"}


def test_run_provider_proposal_eval_separates_known_deferred_and_tripwires() -> None:
    deferred_case = _eval_case(name="deferred_case", deferred=True)
    provider = _SequenceProvider(
        question_interpreter.ProviderFailure("still unsupported"),
        test_support.question_frame_proposal(),
    )

    report = proposal_eval.run_provider_proposal_eval(
        provider=provider,
        semantic_layer=semantic_layer_testing.semantic_layer_with_table(),
        cases=(deferred_case, deferred_case),
        sample_count=1,
    )

    assert report.passes == ()
    assert report.failures == ()
    assert len(report.known_deferred) == 1
    assert report.known_deferred[0].case_name == "deferred_case"
    assert len(report.tripwires) == 1
    assert report.tripwires[0].case_name == "deferred_case"


def test_run_provider_proposal_eval_can_evaluate_cases_concurrently() -> None:
    progress_file = io.StringIO()
    provider = _ConcurrentStartProvider(expected_call_count=2)

    report = proposal_eval.run_provider_proposal_eval(
        provider=provider,
        semantic_layer=semantic_layer_testing.semantic_layer_with_table(),
        cases=(_eval_case(name="alpha"), _eval_case(name="beta")),
        sample_count=1,
        concurrency=2,
        progress=True,
        progress_file=progress_file,
    )

    assert [passed.case_name for passed in report.passes] == ["alpha", "beta"]
    assert len(provider.calls) == 2
    progress_output = progress_file.getvalue()
    assert "Provider Proposal Eval completed 1/2:" in progress_output
    assert "Provider Proposal Eval completed 2/2:" in progress_output


def test_select_cases_supports_range_and_only_cases() -> None:
    cases = _selection_cases()

    assert proposal_eval.select_cases(cases, start_at=2, stop_at=3) == (
        (2, cases[1]),
        (3, cases[2]),
    )
    assert proposal_eval.select_cases(cases, only_cases=("1", "gamma")) == (
        (1, cases[0]),
        (3, cases[2]),
    )


@pytest.mark.parametrize(
    ("start_at", "stop_at", "only_cases", "message"),
    (
        (
            2,
            None,
            ("alpha",),
            "--only-cases cannot be combined with --start-at or --stop-at",
        ),
        (
            2,
            4,
            None,
            "invalid case range: require 1 <= start (2) <= stop (4) <= "
            "enabled count (3)",
        ),
        (
            1,
            None,
            ("9",),
            "--only-cases index out of range: 9 (enabled count 3)",
        ),
        (
            1,
            None,
            ("missing",),
            "--only-cases unknown case name: missing",
        ),
    ),
)
def test_select_cases_rejects_invalid_selection(
    start_at: int,
    stop_at: int | None,
    only_cases: tuple[str, ...] | None,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=re.escape(message)):
        proposal_eval.select_cases(
            _selection_cases(),
            start_at=start_at,
            stop_at=stop_at,
            only_cases=only_cases,
        )


def test_run_provider_proposal_eval_rejects_invalid_concurrency() -> None:
    provider = _SequenceProvider(test_support.question_frame_proposal())

    with pytest.raises(ValueError, match="concurrency must be at least 1"):
        proposal_eval.run_provider_proposal_eval(
            provider=provider,
            semantic_layer=semantic_layer_testing.semantic_layer_with_table(),
            cases=(_eval_case(),),
            concurrency=0,
        )

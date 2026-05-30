import datetime
import io

import data_assistant.live_question_interpreter_eval as live_eval
import data_assistant.question_interpreter as question_interpreter
import data_assistant.question_interpreter_test_support as test_support
import data_assistant.semantic_layer.testing_support as semantic_layer_testing


def test_compare_proposal_matches_exact_meaning_ignoring_time_range_label() -> None:
    expected = test_support.question_frame_proposal()
    actual = test_support.question_frame_proposal(
        time_range=question_interpreter.TimeRangeProposal(
            label="Jan 2026",
            start_date=datetime.date(2026, 1, 1),
            end_date=datetime.date(2026, 1, 31),
        )
    )

    mismatches = live_eval.compare_question_frame_meaning(
        expected=expected,
        actual=actual,
    )

    assert mismatches == ()


def test_compare_proposal_reports_field_level_mismatches() -> None:
    expected = test_support.question_frame_proposal()
    actual = test_support.question_frame_proposal(
        intent="trend",
        metric="gross margin",
        dimension="country",
        time_range=question_interpreter.TimeRangeProposal(
            label="February 2026",
            start_date=datetime.date(2026, 2, 1),
            end_date=datetime.date(2026, 2, 28),
        ),
        filters=("region = 'North'",),
    )

    mismatches = live_eval.compare_question_frame_meaning(
        expected=expected,
        actual=actual,
    )

    assert mismatches == (
        "intent: expected 'summarize', got 'trend'",
        "metric: expected 'total revenue', got 'gross margin'",
        "dimension: expected 'region', got 'country'",
        "filters: expected (), got (\"region = 'North'\",)",
        "time_range.start_date: expected 2026-01-01, got 2026-02-01",
        "time_range.end_date: expected 2026-01-31, got 2026-02-28",
    )


def test_run_eval_suite_reports_all_failures_without_fail_fast() -> None:
    class FakeProvider:
        def __init__(self) -> None:
            self.calls: list[str] = []

        def propose_question_frame(
            self,
            *,
            question: str,
            semantic_layer_context: dict[str, object],
        ) -> live_eval.ProviderResult:
            del semantic_layer_context
            self.calls.append(question)
            if question == "passing":
                return test_support.question_frame_proposal()
            if question == "bad metric":
                return test_support.question_frame_proposal(metric="gross margin")
            return question_interpreter.ProviderFailure(reason="provider offline")

    provider = FakeProvider()
    cases = (
        live_eval.LiveEvalCase(
            name="passing_case",
            question="passing",
            expected=test_support.question_frame_proposal(),
        ),
        live_eval.LiveEvalCase(
            name="mismatch_case",
            question="bad metric",
            expected=test_support.question_frame_proposal(),
        ),
        live_eval.LiveEvalCase(
            name="provider_failure_case",
            question="provider failure",
            expected=test_support.question_frame_proposal(),
        ),
    )

    report = live_eval.run_live_question_interpreter_eval(
        provider=provider,
        semantic_layer=semantic_layer_testing.semantic_layer_with_table(),
        cases=cases,
    )

    assert report.total == 3
    assert report.passed == 1
    assert len(report.failures) == 2
    assert report.failures[0].case_name == "mismatch_case"
    assert report.failures[0].reasons == (
        "metric: expected 'total revenue', got 'gross margin'",
    )
    assert report.failures[1].case_name == "provider_failure_case"
    assert report.failures[1].reasons == ("provider failure: provider offline",)
    assert provider.calls == ["passing", "bad metric", "provider failure"]


def test_main_returns_one_and_prints_missing_api_key_error() -> None:
    stdout = io.StringIO()
    stderr = io.StringIO()

    exit_code = live_eval.main(stdout=stdout, stderr=stderr, environ={})

    assert exit_code == 1
    assert stdout.getvalue() == ""
    assert stderr.getvalue().strip() == (
        "Missing required OpenAI environment variables: OPENAI_API_KEY"
    )

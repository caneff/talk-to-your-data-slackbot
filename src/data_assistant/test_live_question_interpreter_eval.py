import collections.abc
import io
import pathlib
import typing

import pytest

import data_assistant.live_question_interpreter_eval as live_eval
import data_assistant.question_interpreter as question_interpreter
import data_assistant.question_interpreter_test_support as test_support
import data_assistant.semantic_layer.schema as schema
import data_assistant.semantic_layer.testing_support as semantic_layer_testing


def test_compare_proposal_matches_exact_meaning() -> None:
    expected = test_support.question_frame_proposal()
    actual = test_support.question_frame_proposal()

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
        field_operations=(
            question_interpreter.GroupByOperationProposal(
                operation="group_by",
                field="country",
            ),
            question_interpreter.IncludeFilterOperationProposal(
                operation="include_filter",
                field="region",
                values=("North",),
            ),
        ),
    )

    mismatches = live_eval.compare_question_frame_meaning(
        expected=expected,
        actual=actual,
    )

    assert mismatches == (
        "intent: expected 'summarize', got 'trend'",
        "metric: expected 'total revenue', got 'gross margin'",
        "field_operations: expected "
        "(GroupByOperationProposal(operation='group_by', field='region'), "
        "RangeFilterOperationProposal(operation='range_filter', field='order date', "
        "lower=datetime.date(2026, 1, 1), upper=datetime.date(2026, 1, 31))), "
        "got (GroupByOperationProposal(operation='group_by', field='country'), "
        "IncludeFilterOperationProposal(operation='include_filter', field='region', "
        "values=('North',)))",
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
    assert report.passes[0].case_name == "passing_case"
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


def test_write_report_hides_passed_case_details_by_default() -> None:
    stdout = io.StringIO()
    report = live_eval.LiveEvalReport(
        total=1,
        passes=(
            live_eval.LiveEvalPass(
                case_name="passing_case",
                question="passing",
                expected=test_support.question_frame_proposal(),
                actual=test_support.question_frame_proposal(),
            ),
        ),
        failures=(),
    )

    live_eval.write_live_eval_report(stdout=stdout, report=report)

    assert stdout.getvalue() == "Total cases: 1\nPassed: 1\nFailed: 0\n"


def test_write_report_verbose_prints_passed_case_details() -> None:
    stdout = io.StringIO()
    report = live_eval.LiveEvalReport(
        total=1,
        passes=(
            live_eval.LiveEvalPass(
                case_name="passing_case",
                question="passing",
                expected=test_support.question_frame_proposal(),
                actual=test_support.question_frame_proposal(),
            ),
        ),
        failures=(),
    )

    live_eval.write_live_eval_report(stdout=stdout, report=report, verbose=True)

    output = stdout.getvalue()
    assert "Total cases: 1\nPassed: 1\nFailed: 0\n" in output
    assert "[PASS] passing_case" in output
    assert "Question: passing" in output
    assert 'Expected: {"intent":"summarize"' in output
    assert 'Actual: {"intent":"summarize"' in output


def test_main_loads_openai_config_from_dotenv(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: pathlib.Path,
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("OPENAI_API_KEY=dotenv-key\n", encoding="utf-8")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    class FakeProvider:
        def propose_question_frame(
            self,
            *,
            question: str,
            semantic_layer_context: dict[str, object],
        ) -> live_eval.ProviderResult:
            del question, semantic_layer_context
            raise AssertionError("live eval runner is stubbed")

    def fake_build_openai_provider(
        environ: collections.abc.Mapping[str, str],
    ) -> question_interpreter.QuestionInterpreterProvider:
        assert environ["OPENAI_API_KEY"] == "dotenv-key"
        return FakeProvider()

    def fake_run_live_eval(
        *,
        provider: question_interpreter.QuestionInterpreterProvider,
        semantic_layer: schema.SemanticLayer,
        cases: collections.abc.Iterable[live_eval.LiveEvalCase] = (
            live_eval.DEFAULT_CASES
        ),
    ) -> live_eval.LiveEvalReport:
        del provider, semantic_layer, cases
        return live_eval.LiveEvalReport(total=0, passes=(), failures=())

    monkeypatch.setattr(
        live_eval.question_interpreter,
        "build_openai_question_interpreter_provider",
        fake_build_openai_provider,
    )
    monkeypatch.setattr(
        live_eval,
        "run_live_question_interpreter_eval",
        fake_run_live_eval,
    )

    exit_code = live_eval.main(
        stdout=io.StringIO(),
        stderr=io.StringIO(),
        env_file=env_file,
    )

    assert exit_code == 0


def test_main_passes_verbose_flag_to_report_writer(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: pathlib.Path,
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("OPENAI_API_KEY=dotenv-key\n", encoding="utf-8")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    captured_verbose: list[bool] = []

    class FakeProvider:
        def propose_question_frame(
            self,
            *,
            question: str,
            semantic_layer_context: dict[str, object],
        ) -> live_eval.ProviderResult:
            del question, semantic_layer_context
            raise AssertionError("live eval runner is stubbed")

    def fake_build_openai_provider(
        environ: collections.abc.Mapping[str, str],
    ) -> question_interpreter.QuestionInterpreterProvider:
        assert environ["OPENAI_API_KEY"] == "dotenv-key"
        return FakeProvider()

    def fake_run_live_eval(
        *,
        provider: question_interpreter.QuestionInterpreterProvider,
        semantic_layer: schema.SemanticLayer,
        cases: collections.abc.Iterable[live_eval.LiveEvalCase] = (
            live_eval.DEFAULT_CASES
        ),
    ) -> live_eval.LiveEvalReport:
        del provider, semantic_layer, cases
        return live_eval.LiveEvalReport(total=0, passes=(), failures=())

    def fake_write_report(
        *,
        stdout: typing.TextIO,
        report: live_eval.LiveEvalReport,
        verbose: bool = False,
    ) -> None:
        del stdout, report
        captured_verbose.append(verbose)

    monkeypatch.setattr(
        live_eval.question_interpreter,
        "build_openai_question_interpreter_provider",
        fake_build_openai_provider,
    )
    monkeypatch.setattr(
        live_eval,
        "run_live_question_interpreter_eval",
        fake_run_live_eval,
    )
    monkeypatch.setattr(live_eval, "write_live_eval_report", fake_write_report)

    exit_code = live_eval.main(
        stdout=io.StringIO(),
        stderr=io.StringIO(),
        env_file=env_file,
        argv=("--verbose",),
    )

    assert exit_code == 0
    assert captured_verbose == [True]

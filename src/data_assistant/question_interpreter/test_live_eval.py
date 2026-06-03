import collections.abc
import io
import pathlib
import typing

import pytest

import data_assistant.question_interpreter as question_interpreter
import data_assistant.question_interpreter.live_eval as live_eval
import data_assistant.question_interpreter.question_frame_cases as question_frame_cases
import data_assistant.question_interpreter.test_support as test_support
import data_assistant.semantic_layer.catalog as semantic_layer_catalog
import data_assistant.semantic_layer.loader as semantic_layer_loader
import data_assistant.semantic_layer.testing_support as semantic_layer_testing
import data_assistant.slack_runtime as slack_runtime


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
        "field_operations[0].field: expected 'region', got 'country'",
        "field_operations[1].operation: expected 'range_filter', got 'include_filter'",
        "field_operations[1].field: expected 'order date', got 'region'",
        "field_operations[1].lower: expected '2026-01-01', got None",
        "field_operations[1].upper: expected '2026-01-31', got None",
        "field_operations[1].values: expected (), got ('North',)",
    )


def test_compare_proposal_reports_missing_field_operation() -> None:
    expected = test_support.question_frame_proposal()
    actual = test_support.question_frame_proposal(
        field_operations=(
            question_interpreter.GroupByOperationProposal(
                operation="group_by",
                field="region",
            ),
        ),
    )

    mismatches = live_eval.compare_question_frame_meaning(
        expected=expected,
        actual=actual,
    )

    assert mismatches == (
        'field_operations[1]: expected {"operation":"range_filter",'
        '"field":"order date","lower":"2026-01-01","upper":"2026-01-31",'
        '"values":[]}, got (missing)',
    )


def test_compare_proposal_reports_extra_field_operation() -> None:
    expected = test_support.question_frame_proposal(
        field_operations=(
            question_interpreter.GroupByOperationProposal(
                operation="group_by",
                field="region",
            ),
        ),
    )
    actual = test_support.question_frame_proposal(
        field_operations=(
            question_interpreter.GroupByOperationProposal(
                operation="group_by",
                field="region",
            ),
            question_interpreter.ExcludeFilterOperationProposal(
                operation="exclude_filter",
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
        'field_operations[1]: expected (missing), got {"operation":'
        '"exclude_filter","field":"region","lower":null,"upper":null,'
        '"values":["North"]}',
    )


def test_compare_proposal_reports_all_time_mismatch() -> None:
    expected = test_support.question_frame_proposal()
    actual = test_support.question_frame_proposal(all_time=True)

    mismatches = live_eval.compare_question_frame_meaning(
        expected=expected,
        actual=actual,
    )

    assert mismatches == ("all_time: expected False, got True",)


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

    progress_file = io.StringIO()
    report = live_eval.run_live_question_interpreter_eval(
        provider=provider,
        semantic_layer=semantic_layer_testing.semantic_layer_with_table(),
        cases=cases,
        progress=True,
        progress_file=progress_file,
    )

    assert report.total == 3
    assert report.passed == 1
    assert report.passes[0].case_name == "passing_case"
    assert report.passes[0].pass_count == 3
    assert report.passes[0].sample_count == 3
    assert len(report.failures) == 2
    assert report.failures[0].case_name == "mismatch_case"
    assert report.failures[0].reasons == (
        "sample 1: metric: expected 'total revenue', got 'gross margin'",
        "sample 2: metric: expected 'total revenue', got 'gross margin'",
        "sample 3: metric: expected 'total revenue', got 'gross margin'",
    )
    assert report.failures[1].case_name == "provider_failure_case"
    assert report.failures[1].reasons == (
        "sample 1: provider failure: provider offline",
        "sample 2: provider failure: provider offline",
        "sample 3: provider failure: provider offline",
    )
    assert provider.calls == [
        "passing",
        "passing",
        "passing",
        "bad metric",
        "bad metric",
        "bad metric",
        "provider failure",
        "provider failure",
        "provider failure",
    ]
    progress_output = progress_file.getvalue()
    assert "Live eval cases 1/3: passing_case" in progress_output
    assert "Live eval cases 2/3: mismatch_case" in progress_output
    assert "Live eval cases 3/3: provider_failure_case" in progress_output


def test_run_eval_suite_requires_all_samples_to_match_for_case_pass() -> None:
    class FakeProvider:
        def __init__(self) -> None:
            self.calls: list[str] = []
            self.results = [
                test_support.question_frame_proposal(),
                test_support.question_frame_proposal(metric="gross margin"),
                test_support.question_frame_proposal(),
            ]

        def propose_question_frame(
            self,
            *,
            question: str,
            semantic_layer_context: dict[str, object],
        ) -> live_eval.ProviderResult:
            del semantic_layer_context
            self.calls.append(question)
            return self.results[len(self.calls) - 1]

    provider = FakeProvider()
    cases = (
        live_eval.LiveEvalCase(
            name="flaky_case",
            question="flaky",
            expected=test_support.question_frame_proposal(),
        ),
    )

    report = live_eval.run_live_question_interpreter_eval(
        provider=provider,
        semantic_layer=semantic_layer_testing.semantic_layer_with_table(),
        cases=cases,
        sample_count=3,
    )

    assert report.total == 1
    assert report.passed == 0
    assert report.failed == 1
    assert report.failures[0].case_name == "flaky_case"
    assert report.failures[0].pass_count == 2
    assert report.failures[0].sample_count == 3
    assert report.failures[0].reasons == (
        "sample 2: metric: expected 'total revenue', got 'gross margin'",
    )
    assert report.failures[0].actual == test_support.question_frame_proposal(
        metric="gross margin",
    )
    assert provider.calls == ["flaky", "flaky", "flaky"]


def test_run_eval_suite_counts_provider_failure_as_sample_failure() -> None:
    class FakeProvider:
        def __init__(self) -> None:
            self.calls: list[str] = []
            self.results: list[live_eval.ProviderResult] = [
                question_interpreter.ProviderFailure(
                    reason=(
                        "1 validation error for QuestionFrameProposal\n"
                        "  Invalid JSON: EOF while parsing a value at line 1 "
                        "column 0"
                    )
                ),
                test_support.question_frame_proposal(),
                test_support.question_frame_proposal(),
                test_support.question_frame_proposal(),
            ]

        def propose_question_frame(
            self,
            *,
            question: str,
            semantic_layer_context: dict[str, object],
        ) -> live_eval.ProviderResult:
            del semantic_layer_context
            self.calls.append(question)
            return self.results[len(self.calls) - 1]

    provider = FakeProvider()
    cases = (
        live_eval.LiveEvalCase(
            name="transient_parse_failure_case",
            question="flaky provider",
            expected=test_support.question_frame_proposal(),
        ),
    )

    report = live_eval.run_live_question_interpreter_eval(
        provider=provider,
        semantic_layer=semantic_layer_testing.semantic_layer_with_table(),
        cases=cases,
        sample_count=3,
    )

    assert report.total == 1
    assert report.passed == 0
    assert report.failed == 1
    assert report.failures[0].case_name == "transient_parse_failure_case"
    assert report.failures[0].pass_count == 2
    assert report.failures[0].sample_count == 3
    assert report.failures[0].reasons == (
        "sample 1: provider failure: "
        "1 validation error for QuestionFrameProposal\n"
        "  Invalid JSON: EOF while parsing a value at line 1 column 0",
    )
    assert provider.calls == ["flaky provider", "flaky provider", "flaky provider"]


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

    assert stdout.getvalue() == (
        "Total cases: 1\nPassed: 1\nFailed: 0\n[PASS] passing_case (pass rate: 1/1)\n"
    )


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
    assert (
        "Total cases: 1\nPassed: 1\nFailed: 0\n[PASS] passing_case (pass rate: 1/1)\n"
    ) in output
    assert "Question: passing" in output
    assert 'Expected: {"intent":"summarize"' in output
    assert 'Actual: {"intent":"summarize"' in output


def test_write_report_includes_failure_pass_rate() -> None:
    stdout = io.StringIO()
    report = live_eval.LiveEvalReport(
        total=1,
        passes=(),
        failures=(
            live_eval.LiveEvalFailure(
                case_name="flaky_case",
                question="flaky",
                expected=test_support.question_frame_proposal(),
                actual=test_support.question_frame_proposal(metric="gross margin"),
                reasons=(
                    "sample 2: metric: expected 'total revenue', got 'gross margin'",
                ),
                pass_count=2,
                sample_count=3,
            ),
        ),
    )

    live_eval.write_live_eval_report(stdout=stdout, report=report)

    output = stdout.getvalue()
    assert "Total cases: 1\nPassed: 0\nFailed: 1\n" in output
    assert "[FAIL] flaky_case (pass rate: 2/3)" in output


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
        semantic_layer: semantic_layer_catalog.SemanticLayerCatalog,
        cases: collections.abc.Iterable[live_eval.LiveEvalCase] = (
            live_eval.DEFAULT_CASES
        ),
        progress: bool = False,
        progress_file: typing.TextIO | None = None,
    ) -> live_eval.LiveEvalReport:
        del provider, semantic_layer, cases, progress, progress_file
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
        semantic_layer: semantic_layer_catalog.SemanticLayerCatalog,
        cases: collections.abc.Iterable[live_eval.LiveEvalCase] = (
            live_eval.DEFAULT_CASES
        ),
        progress: bool = False,
        progress_file: typing.TextIO | None = None,
    ) -> live_eval.LiveEvalReport:
        del provider, semantic_layer, cases, progress, progress_file
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


def test_main_enables_progress_by_default_and_accepts_no_progress(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: pathlib.Path,
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("OPENAI_API_KEY=dotenv-key\n", encoding="utf-8")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    captured_progress: list[bool] = []
    captured_progress_files: list[typing.TextIO | None] = []

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
        semantic_layer: semantic_layer_catalog.SemanticLayerCatalog,
        cases: collections.abc.Iterable[live_eval.LiveEvalCase] = (
            live_eval.DEFAULT_CASES
        ),
        progress: bool = False,
        progress_file: typing.TextIO | None = None,
    ) -> live_eval.LiveEvalReport:
        del provider, semantic_layer, cases
        captured_progress.append(progress)
        captured_progress_files.append(progress_file)
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

    default_stderr = io.StringIO()
    no_progress_stderr = io.StringIO()
    default_exit_code = live_eval.main(
        stdout=io.StringIO(),
        stderr=default_stderr,
        env_file=env_file,
    )
    no_progress_exit_code = live_eval.main(
        stdout=io.StringIO(),
        stderr=no_progress_stderr,
        env_file=env_file,
        argv=("--no-progress",),
    )

    assert default_exit_code == 0
    assert no_progress_exit_code == 0
    assert captured_progress == [True, False]
    assert captured_progress_files == [default_stderr, no_progress_stderr]


def test_main_returns_one_when_live_eval_report_has_failures(
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
        semantic_layer: semantic_layer_catalog.SemanticLayerCatalog,
        cases: collections.abc.Iterable[live_eval.LiveEvalCase] = (
            live_eval.DEFAULT_CASES
        ),
        sample_count: int = live_eval.DEFAULT_SAMPLE_COUNT,
        progress: bool = False,
        progress_file: typing.TextIO | None = None,
    ) -> live_eval.LiveEvalReport:
        del provider, semantic_layer, cases, sample_count, progress, progress_file
        return live_eval.LiveEvalReport(
            total=1,
            passes=(),
            failures=(
                live_eval.LiveEvalFailure(
                    case_name="flaky_case",
                    question="flaky",
                    expected=test_support.question_frame_proposal(),
                    actual=test_support.question_frame_proposal(metric="gross margin"),
                    reasons=(
                        "sample 2: metric: expected 'total revenue', got "
                        "'gross margin'",
                    ),
                    pass_count=2,
                    sample_count=3,
                ),
            ),
        )

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

    assert exit_code == 1


def test_default_live_eval_cases_come_from_shared_question_frame_cases() -> None:
    assert (
        tuple(
            live_eval.LiveEvalCase(
                name=case.name,
                question=case.question,
                expected=case.expected,
                enabled=case.enabled,
            )
            for case in question_frame_cases.SHARED_QUESTION_FRAME_CASES
        )
        == live_eval.DEFAULT_CASES
    )


def test_default_live_eval_includes_customer_count_by_customer_region_case() -> None:
    case = next(
        case
        for case in live_eval.DEFAULT_CASES
        if case.name == "customer_count_by_customer_region"
    )

    assert case.enabled is True
    assert case.question == (
        "What was customer count by customer region in January 2026?"
    )
    assert case.expected == question_interpreter.QuestionFrameProposal(
        intent="summarize",
        metric="customer count",
        field_operations=(
            question_interpreter.GroupByOperationProposal(
                operation="group_by",
                field="customer region",
            ),
            question_interpreter.RangeFilterOperationProposal(
                operation="range_filter",
                field="customer created date",
                lower="2026-01-01",
                upper="2026-01-31",
            ),
        ),
    )


def test_default_live_eval_includes_exact_date_net_revenue_case() -> None:
    case = next(
        case
        for case in live_eval.DEFAULT_CASES
        if case.name == "exact_date_net_revenue"
    )

    assert case.enabled is True
    assert case.question == "What was total net revenue on 2026-01-15?"
    assert case.expected == question_interpreter.QuestionFrameProposal(
        intent="summarize",
        metric="total net revenue",
        field_operations=(
            question_interpreter.IncludeFilterOperationProposal(
                operation="include_filter",
                field="order date",
                values=("2026-01-15",),
            ),
        ),
    )


def test_default_live_eval_includes_multi_filter_net_revenue_case() -> None:
    case = next(
        case
        for case in live_eval.DEFAULT_CASES
        if case.name == "multi_filter_net_revenue"
    )

    assert case.enabled is True
    assert case.question == (
        "What was total net revenue for the Web order channel and Shipped "
        "fulfillment status for all time?"
    )
    assert case.expected == question_interpreter.QuestionFrameProposal(
        intent="summarize",
        metric="total net revenue",
        all_time=True,
        field_operations=(
            question_interpreter.IncludeFilterOperationProposal(
                operation="include_filter",
                field="order channel",
                values=("Web",),
            ),
            question_interpreter.IncludeFilterOperationProposal(
                operation="include_filter",
                field="fulfillment status",
                values=("Shipped",),
            ),
        ),
    )


def test_main_loads_real_semantic_layer_for_live_eval(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: pathlib.Path,
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("OPENAI_API_KEY=dotenv-key\n", encoding="utf-8")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    loaded_semantic_layer = semantic_layer_testing.semantic_layer_with_table()
    captured_semantic_layers: list[semantic_layer_catalog.SemanticLayerCatalog] = []
    captured_paths: list[pathlib.Path] = []

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

    def fake_load_semantic_layer(
        path: pathlib.Path = semantic_layer_loader.DEFAULT_SEMANTIC_LAYER_PATH,
    ) -> semantic_layer_catalog.SemanticLayerCatalog:
        captured_paths.append(path)
        return loaded_semantic_layer

    def fake_run_live_eval(
        *,
        provider: question_interpreter.QuestionInterpreterProvider,
        semantic_layer: semantic_layer_catalog.SemanticLayerCatalog,
        cases: collections.abc.Iterable[live_eval.LiveEvalCase] = (
            live_eval.DEFAULT_CASES
        ),
        progress: bool = False,
        progress_file: typing.TextIO | None = None,
    ) -> live_eval.LiveEvalReport:
        del provider, cases, progress, progress_file
        captured_semantic_layers.append(semantic_layer)
        return live_eval.LiveEvalReport(total=0, passes=(), failures=())

    monkeypatch.setattr(
        live_eval.question_interpreter,
        "build_openai_question_interpreter_provider",
        fake_build_openai_provider,
    )
    monkeypatch.setattr(
        semantic_layer_loader,
        "load_semantic_layer",
        fake_load_semantic_layer,
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
    assert captured_semantic_layers == [loaded_semantic_layer]
    assert captured_paths == [slack_runtime.RETAIL_SEMANTIC_LAYER_PATH]

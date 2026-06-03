import collections.abc
import io
import json
import pathlib
import types
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


class _SelectCasesKwargs(typing.TypedDict):
    start_at: int
    stop_at: int | None
    only_cases: tuple[str, ...] | None


def _recording_run_live_eval(
    calls: list[types.SimpleNamespace],
) -> collections.abc.Callable[..., live_eval.LiveEvalReport]:
    """Build a `run_live_question_interpreter_eval` stub that records its call.

    Each test inspects only the keyword(s) it cares about on the recorded
    `SimpleNamespace`, and the stub returns an empty report.
    """

    def _fake(
        *,
        provider: question_interpreter.QuestionInterpreterProvider,
        semantic_layer: semantic_layer_catalog.SemanticLayerCatalog,
        cases: collections.abc.Iterable[live_eval.LiveEvalCase] = (
            live_eval.DEFAULT_CASES
        ),
        sample_count: int = live_eval.DEFAULT_SAMPLE_COUNT,
        progress: bool = False,
        progress_file: typing.TextIO | None = None,
        failures_file: typing.TextIO | None = None,
        start_at: int = 1,
        stop_at: int | None = None,
        only_cases: tuple[str, ...] | None = None,
    ) -> live_eval.LiveEvalReport:
        calls.append(
            types.SimpleNamespace(
                provider=provider,
                semantic_layer=semantic_layer,
                cases=cases,
                sample_count=sample_count,
                progress=progress,
                progress_file=progress_file,
                failures_file=failures_file,
                start_at=start_at,
                stop_at=stop_at,
                only_cases=only_cases,
            )
        )
        return live_eval.LiveEvalReport(total=0, passes=(), failures=())

    return _fake


def _stub_load_semantic_layer(
    path: pathlib.Path = semantic_layer_loader.DEFAULT_SEMANTIC_LAYER_PATH,
) -> semantic_layer_catalog.SemanticLayerCatalog:
    del path
    return semantic_layer_testing.semantic_layer_with_table()


def _isolate_main_for_default_failures_file(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: pathlib.Path,
) -> None:
    """Chdir into ``tmp_path`` and stub the semantic-layer load.

    ``main()`` opens a default failures file under ``eval_results/`` relative to
    the cwd, so tests chdir into ``tmp_path`` to keep that artifact out of the
    repo. The chdir would otherwise break the eager (relative-path) semantic
    layer load, so it is stubbed to a small in-memory catalog.
    """
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        semantic_layer_loader,
        "load_semantic_layer",
        _stub_load_semantic_layer,
    )


class _StubProvider:
    """Provider whose ``propose_question_frame`` must never be reached.

    The ``main()`` tests stub the runner, so the real provider is never called;
    if it is, the test should fail loudly rather than make a paid request.
    """

    def propose_question_frame(
        self,
        *,
        question: str,
        semantic_layer_context: dict[str, object],
    ) -> live_eval.ProviderResult:
        del question, semantic_layer_context
        raise AssertionError("live eval runner is stubbed")


def _build_stub_provider(
    environ: collections.abc.Mapping[str, str],
) -> _StubProvider:
    del environ
    return _StubProvider()


@pytest.fixture
def stub_main(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: pathlib.Path,
) -> types.SimpleNamespace:
    """Wire ``main()`` for offline tests: dotenv, provider build, and isolation.

    Leaves the runner unstubbed so tests opt into ``_recording_run_live_eval``
    only when they need to inspect (or replace) the runner call.
    """
    env_file = tmp_path / ".env"
    env_file.write_text("OPENAI_API_KEY=dotenv-key\n", encoding="utf-8")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(
        live_eval.question_interpreter,
        "build_openai_question_interpreter_provider",
        _build_stub_provider,
    )
    _isolate_main_for_default_failures_file(monkeypatch, tmp_path)
    return types.SimpleNamespace(env_file=env_file, tmp_path=tmp_path)


def _jsonable(obj: object) -> object:
    """Round-trip ``obj`` through JSON so tuples compare as the streamed lists."""
    return json.loads(json.dumps(obj))


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
    stub_main: types.SimpleNamespace,
) -> None:
    def assert_dotenv_provider(
        environ: collections.abc.Mapping[str, str],
    ) -> question_interpreter.QuestionInterpreterProvider:
        assert environ["OPENAI_API_KEY"] == "dotenv-key"
        return _StubProvider()

    calls: list[types.SimpleNamespace] = []
    monkeypatch.setattr(
        live_eval.question_interpreter,
        "build_openai_question_interpreter_provider",
        assert_dotenv_provider,
    )
    monkeypatch.setattr(
        live_eval,
        "run_live_question_interpreter_eval",
        _recording_run_live_eval(calls),
    )

    exit_code = live_eval.main(
        stdout=io.StringIO(),
        stderr=io.StringIO(),
        env_file=stub_main.env_file,
    )

    assert exit_code == 0
    assert len(calls) == 1


def test_main_passes_verbose_flag_to_report_writer(
    monkeypatch: pytest.MonkeyPatch,
    stub_main: types.SimpleNamespace,
) -> None:
    captured_verbose: list[bool] = []

    def fake_write_report(
        *,
        stdout: typing.TextIO,
        report: live_eval.LiveEvalReport,
        verbose: bool = False,
    ) -> None:
        del stdout, report
        captured_verbose.append(verbose)

    calls: list[types.SimpleNamespace] = []
    monkeypatch.setattr(
        live_eval,
        "run_live_question_interpreter_eval",
        _recording_run_live_eval(calls),
    )
    monkeypatch.setattr(live_eval, "write_live_eval_report", fake_write_report)

    exit_code = live_eval.main(
        stdout=io.StringIO(),
        stderr=io.StringIO(),
        env_file=stub_main.env_file,
        argv=("--verbose",),
    )

    assert exit_code == 0
    assert captured_verbose == [True]


def test_main_passes_samples_flag_to_live_eval(
    monkeypatch: pytest.MonkeyPatch,
    stub_main: types.SimpleNamespace,
) -> None:
    calls: list[types.SimpleNamespace] = []
    monkeypatch.setattr(
        live_eval,
        "run_live_question_interpreter_eval",
        _recording_run_live_eval(calls),
    )

    default_exit_code = live_eval.main(
        stdout=io.StringIO(),
        stderr=io.StringIO(),
        env_file=stub_main.env_file,
    )
    explicit_exit_code = live_eval.main(
        stdout=io.StringIO(),
        stderr=io.StringIO(),
        env_file=stub_main.env_file,
        argv=("--samples", "7"),
    )

    assert default_exit_code == 0
    assert explicit_exit_code == 0
    assert [call.sample_count for call in calls] == [
        live_eval.DEFAULT_SAMPLE_COUNT,
        7,
    ]


def test_main_enables_progress_by_default_and_accepts_no_progress(
    monkeypatch: pytest.MonkeyPatch,
    stub_main: types.SimpleNamespace,
) -> None:
    calls: list[types.SimpleNamespace] = []
    monkeypatch.setattr(
        live_eval,
        "run_live_question_interpreter_eval",
        _recording_run_live_eval(calls),
    )

    default_stderr = io.StringIO()
    no_progress_stderr = io.StringIO()
    default_exit_code = live_eval.main(
        stdout=io.StringIO(),
        stderr=default_stderr,
        env_file=stub_main.env_file,
    )
    no_progress_exit_code = live_eval.main(
        stdout=io.StringIO(),
        stderr=no_progress_stderr,
        env_file=stub_main.env_file,
        argv=("--no-progress",),
    )

    assert default_exit_code == 0
    assert no_progress_exit_code == 0
    assert [call.progress for call in calls] == [True, False]
    assert [call.progress_file for call in calls] == [
        default_stderr,
        no_progress_stderr,
    ]


def test_main_returns_one_when_live_eval_report_has_failures(
    monkeypatch: pytest.MonkeyPatch,
    stub_main: types.SimpleNamespace,
) -> None:
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
        failures_file: typing.TextIO | None = None,
        start_at: int = 1,
        stop_at: int | None = None,
        only_cases: tuple[str, ...] | None = None,
    ) -> live_eval.LiveEvalReport:
        del provider, semantic_layer, cases, sample_count, progress, progress_file
        del failures_file, start_at, stop_at, only_cases
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
        live_eval,
        "run_live_question_interpreter_eval",
        fake_run_live_eval,
    )

    exit_code = live_eval.main(
        stdout=io.StringIO(),
        stderr=io.StringIO(),
        env_file=stub_main.env_file,
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


def test_shared_cases_cover_every_retail_metric() -> None:
    covered_metrics = {
        case.expected.metric
        for case in question_frame_cases.SHARED_QUESTION_FRAME_CASES
        if case.expected.metric is not None
    }

    assert covered_metrics == {
        "total net revenue",
        "total gross revenue",
        "order count",
        "total discount amount",
        "total line revenue",
        "gross margin",
        "units sold",
        "units returned",
        "customer count",
        "product count",
        "store count",
        "support ticket count",
        "on hand units",
        "stockout days",
    }


def test_shared_cases_cover_every_deferred_intent_once_classified() -> None:
    covered_intents = {
        case.expected.intent
        for case in question_frame_cases.SHARED_QUESTION_FRAME_CASES
    }

    assert {
        "summarize",
        "rank",
        "compare",
        "trend",
        "forecast",
        "explain",
        "prescribe",
        "diagnose",
    } <= covered_intents


def test_shared_cases_use_exclude_filter_on_multiple_field_types() -> None:
    exclude_fields = {
        operation.field
        for case in question_frame_cases.SHARED_QUESTION_FRAME_CASES
        for operation in case.expected.field_operations
        if operation.operation == "exclude_filter"
    }

    assert len(exclude_fields) >= 3


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
    stub_main: types.SimpleNamespace,
) -> None:
    loaded_semantic_layer = semantic_layer_testing.semantic_layer_with_table()
    captured_paths: list[pathlib.Path] = []

    def assert_dotenv_provider(
        environ: collections.abc.Mapping[str, str],
    ) -> question_interpreter.QuestionInterpreterProvider:
        assert environ["OPENAI_API_KEY"] == "dotenv-key"
        return _StubProvider()

    def fake_load_semantic_layer(
        path: pathlib.Path = semantic_layer_loader.DEFAULT_SEMANTIC_LAYER_PATH,
    ) -> semantic_layer_catalog.SemanticLayerCatalog:
        captured_paths.append(path)
        return loaded_semantic_layer

    calls: list[types.SimpleNamespace] = []
    monkeypatch.setattr(
        live_eval.question_interpreter,
        "build_openai_question_interpreter_provider",
        assert_dotenv_provider,
    )
    monkeypatch.setattr(
        semantic_layer_loader,
        "load_semantic_layer",
        fake_load_semantic_layer,
    )
    monkeypatch.setattr(
        live_eval,
        "run_live_question_interpreter_eval",
        _recording_run_live_eval(calls),
    )

    exit_code = live_eval.main(
        stdout=io.StringIO(),
        stderr=io.StringIO(),
        env_file=stub_main.env_file,
    )

    assert exit_code == 0
    assert [call.semantic_layer for call in calls] == [loaded_semantic_layer]
    assert captured_paths == [slack_runtime.RETAIL_SEMANTIC_LAYER_PATH]


def _named_case(name: str) -> live_eval.LiveEvalCase:
    return live_eval.LiveEvalCase(
        name=name,
        question=f"question for {name}",
        expected=test_support.question_frame_proposal(),
    )


def _selected_pairs(
    selected: tuple[tuple[int, live_eval.LiveEvalCase], ...],
) -> list[tuple[int, str]]:
    return [(index, case.name) for index, case in selected]


@pytest.mark.parametrize(
    ("kwargs", "expected_pairs"),
    [
        pytest.param(
            {"start_at": 1, "stop_at": None, "only_cases": None},
            [(1, "a"), (2, "b"), (3, "c")],
            id="defaults_full_enabled_list_absolute_indices",
        ),
        pytest.param(
            {"start_at": 2, "stop_at": None, "only_cases": None},
            [(2, "b"), (3, "c")],
            id="start_at_skips_leading_keeps_absolute_index",
        ),
        pytest.param(
            {"start_at": 2, "stop_at": 3, "only_cases": None},
            [(2, "b"), (3, "c")],
            id="stop_at_inclusive",
        ),
        pytest.param(
            {"start_at": 1, "stop_at": None, "only_cases": ("3", "1")},
            [(1, "a"), (3, "c")],
            id="only_cases_by_index",
        ),
        pytest.param(
            {"start_at": 1, "stop_at": None, "only_cases": ("c", "a")},
            [(1, "a"), (3, "c")],
            id="only_cases_by_name",
        ),
        pytest.param(
            {"start_at": 1, "stop_at": None, "only_cases": ("c", "1", "a", "3")},
            [(1, "a"), (3, "c")],
            id="only_cases_mixed_index_and_name_dedupes_enabled_order",
        ),
    ],
)
def test_select_cases_happy_path(
    kwargs: _SelectCasesKwargs,
    expected_pairs: list[tuple[int, str]],
) -> None:
    enabled = (_named_case("a"), _named_case("b"), _named_case("c"))

    selected = live_eval.select_cases(enabled, **kwargs)

    assert _selected_pairs(selected) == expected_pairs


@pytest.mark.parametrize(
    "kwargs",
    [
        pytest.param(
            {"start_at": 2, "stop_at": None, "only_cases": ("a",)},
            id="only_cases_with_start_or_stop",
        ),
        pytest.param(
            {"start_at": 1, "stop_at": None, "only_cases": ("nope",)},
            id="unknown_name",
        ),
        pytest.param(
            {"start_at": 1, "stop_at": None, "only_cases": ("4",)},
            id="out_of_range_index",
        ),
        pytest.param(
            {"start_at": 0, "stop_at": None, "only_cases": None},
            id="start_below_one",
        ),
        pytest.param(
            {"start_at": 3, "stop_at": 2, "only_cases": None},
            id="stop_below_start",
        ),
        pytest.param(
            {"start_at": 4, "stop_at": None, "only_cases": None},
            id="start_beyond_enabled",
        ),
    ],
)
def test_select_cases_raises_on_invalid_selection(
    kwargs: _SelectCasesKwargs,
) -> None:
    enabled = (_named_case("a"), _named_case("b"), _named_case("c"))

    with pytest.raises(ValueError):
        live_eval.select_cases(enabled, **kwargs)


def _failing_provider() -> question_interpreter.QuestionInterpreterProvider:
    class FakeProvider:
        def propose_question_frame(
            self,
            *,
            question: str,
            semantic_layer_context: dict[str, object],
        ) -> live_eval.ProviderResult:
            del semantic_layer_context
            if question == "passing":
                return test_support.question_frame_proposal()
            if question == "bad metric":
                return test_support.question_frame_proposal(metric="gross margin")
            return question_interpreter.ProviderFailure(reason="provider offline")

    return FakeProvider()


def test_run_eval_streams_failure_line_with_locked_schema() -> None:
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
    )
    failures_file = io.StringIO()

    live_eval.run_live_question_interpreter_eval(
        provider=_failing_provider(),
        semantic_layer=semantic_layer_testing.semantic_layer_with_table(),
        cases=cases,
        sample_count=3,
        failures_file=failures_file,
    )

    lines = [line for line in failures_file.getvalue().splitlines() if line]
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["case_number"] == 2
    assert record["case_name"] == "mismatch_case"
    assert record["question"] == "bad metric"
    assert record["pass_count"] == 0
    assert record["sample_count"] == 3
    assert len(record["reasons"]) == 3
    assert all(isinstance(reason, str) and reason for reason in record["reasons"])
    assert record["expected"] == _jsonable(
        test_support.question_frame_proposal().model_dump()
    )
    assert record["actual"] == _jsonable(
        test_support.question_frame_proposal(metric="gross margin").model_dump()
    )


def test_run_eval_streams_provider_failure_actual() -> None:
    cases = (
        live_eval.LiveEvalCase(
            name="provider_failure_case",
            question="provider failure",
            expected=test_support.question_frame_proposal(),
        ),
    )
    failures_file = io.StringIO()

    live_eval.run_live_question_interpreter_eval(
        provider=_failing_provider(),
        semantic_layer=semantic_layer_testing.semantic_layer_with_table(),
        cases=cases,
        sample_count=1,
        failures_file=failures_file,
    )

    record = json.loads(failures_file.getvalue().strip())
    assert record["case_number"] == 1
    assert record["actual"] == {"provider_failure": "provider offline"}


def test_run_eval_clean_run_leaves_empty_failures_file() -> None:
    cases = (
        live_eval.LiveEvalCase(
            name="passing_case",
            question="passing",
            expected=test_support.question_frame_proposal(),
        ),
    )
    failures_file = io.StringIO()

    live_eval.run_live_question_interpreter_eval(
        provider=_failing_provider(),
        semantic_layer=semantic_layer_testing.semantic_layer_with_table(),
        cases=cases,
        sample_count=2,
        failures_file=failures_file,
    )

    assert failures_file.getvalue() == ""


def test_run_eval_streams_multiple_failures_in_order() -> None:
    cases = (
        live_eval.LiveEvalCase(
            name="mismatch_case",
            question="bad metric",
            expected=test_support.question_frame_proposal(),
        ),
        live_eval.LiveEvalCase(
            name="passing_case",
            question="passing",
            expected=test_support.question_frame_proposal(),
        ),
        live_eval.LiveEvalCase(
            name="provider_failure_case",
            question="provider failure",
            expected=test_support.question_frame_proposal(),
        ),
    )
    failures_file = io.StringIO()

    live_eval.run_live_question_interpreter_eval(
        provider=_failing_provider(),
        semantic_layer=semantic_layer_testing.semantic_layer_with_table(),
        cases=cases,
        sample_count=1,
        failures_file=failures_file,
    )

    records = [
        json.loads(line) for line in failures_file.getvalue().splitlines() if line
    ]
    assert [(r["case_number"], r["case_name"]) for r in records] == [
        (1, "mismatch_case"),
        (3, "provider_failure_case"),
    ]


def test_run_eval_case_number_is_absolute_under_start_at() -> None:
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
    )
    failures_file = io.StringIO()

    report = live_eval.run_live_question_interpreter_eval(
        provider=_failing_provider(),
        semantic_layer=semantic_layer_testing.semantic_layer_with_table(),
        cases=cases,
        sample_count=1,
        failures_file=failures_file,
        start_at=2,
    )

    assert report.total == 1
    record = json.loads(failures_file.getvalue().strip())
    assert record["case_number"] == 2
    assert record["case_name"] == "mismatch_case"


def test_run_eval_only_cases_runs_selected_subset() -> None:
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
    )

    report = live_eval.run_live_question_interpreter_eval(
        provider=_failing_provider(),
        semantic_layer=semantic_layer_testing.semantic_layer_with_table(),
        cases=cases,
        sample_count=1,
        only_cases=("mismatch_case",),
    )

    assert report.total == 1
    assert report.failed == 1
    assert report.failures[0].case_name == "mismatch_case"


def test_main_writes_failures_out_path(
    monkeypatch: pytest.MonkeyPatch,
    stub_main: types.SimpleNamespace,
) -> None:
    failures_path = stub_main.tmp_path / "out.jsonl"
    calls: list[types.SimpleNamespace] = []
    monkeypatch.setattr(
        live_eval,
        "run_live_question_interpreter_eval",
        _recording_run_live_eval(calls),
    )

    exit_code = live_eval.main(
        stdout=io.StringIO(),
        stderr=io.StringIO(),
        env_file=stub_main.env_file,
        argv=("--failures-out", str(failures_path)),
    )

    assert exit_code == 0
    assert failures_path.exists()
    assert len(calls) == 1
    assert calls[0].failures_file is not None


def test_main_default_failures_path_lands_under_eval_results(
    monkeypatch: pytest.MonkeyPatch,
    stub_main: types.SimpleNamespace,
) -> None:
    calls: list[types.SimpleNamespace] = []
    monkeypatch.setattr(
        live_eval,
        "run_live_question_interpreter_eval",
        _recording_run_live_eval(calls),
    )

    exit_code = live_eval.main(
        stdout=io.StringIO(),
        stderr=io.StringIO(),
        env_file=stub_main.env_file,
    )

    assert exit_code == 0
    written = list((stub_main.tmp_path / "eval_results").glob("*.jsonl"))
    assert len(written) == 1
    assert written[0].name.startswith("live_eval_failures_")


def test_main_passes_selection_flags_to_runner(
    monkeypatch: pytest.MonkeyPatch,
    stub_main: types.SimpleNamespace,
) -> None:
    calls: list[types.SimpleNamespace] = []
    monkeypatch.setattr(
        live_eval,
        "run_live_question_interpreter_eval",
        _recording_run_live_eval(calls),
    )

    start_stop_exit = live_eval.main(
        stdout=io.StringIO(),
        stderr=io.StringIO(),
        env_file=stub_main.env_file,
        argv=("--start-at", "3", "--stop-at", "7"),
    )
    only_exit = live_eval.main(
        stdout=io.StringIO(),
        stderr=io.StringIO(),
        env_file=stub_main.env_file,
        argv=("--only-cases", "44,exact_date", "--only-cases", "10"),
    )

    assert start_stop_exit == 0
    assert only_exit == 0
    assert calls[0].start_at == 3
    assert calls[0].stop_at == 7
    assert calls[0].only_cases is None
    assert calls[1].start_at == 1
    assert calls[1].stop_at is None
    assert calls[1].only_cases == ("44", "exact_date", "10")


def test_main_only_cases_with_start_at_is_usage_error() -> None:
    # argparse rejects the flag combination before any env/provider/runner
    # wiring runs, so this test needs none of the main() stubs.
    with pytest.raises(SystemExit) as exit_info:
        live_eval.main(
            stdout=io.StringIO(),
            stderr=io.StringIO(),
            argv=("--only-cases", "1", "--start-at", "2"),
        )

    assert exit_info.value.code != 0


def test_main_bad_range_exits_non_zero_with_message(
    stub_main: types.SimpleNamespace,
) -> None:
    # No runner stub: the REAL runner's select_cases must raise on the bad range.
    stderr = io.StringIO()

    exit_code = live_eval.main(
        stdout=io.StringIO(),
        stderr=stderr,
        env_file=stub_main.env_file,
        argv=("--start-at", "9999"),
    )

    assert exit_code == 1
    assert stderr.getvalue().strip() != ""

import datetime

import pytest

import data_assistant.data_preparation as data_preparation
import data_assistant.data_requester as data_requester
import data_assistant.local_duckdb_fixture as local_duckdb_fixture
import data_assistant.question_interpreter as question_interpreter
import data_assistant.reasoning_layer as reasoning_layer
import data_assistant.reasoning_layer.test_support as reasoning_test_support
import data_assistant.semantic_layer.schema as schema
import data_assistant.workflow.contracts as contracts
import data_assistant.workflow.runner as workflow_runner

EXPECTED_PROGRESS_STATUSES = [
    "understanding your question...",
    "finding the right data...",
    "running the numbers...",
    "writing it up...",
]


def capture_non_answer_response(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[contracts.FinalResponse, list[contracts.NonAnswer]]:
    captured_non_answers: list[contracts.NonAnswer] = []
    sentinel_response = contracts.FinalResponse(
        text="non-answer response",
        trust_summary=contracts.TrustSummary(
            limitations=("non-answer trust summary",),
        ),
        response_kind=contracts.ResponseKind.UNSUPPORTED,
    )

    def compose_non_answer_response(
        non_answer: contracts.NonAnswer,
        *,
        wording_provider: object = None,
    ) -> contracts.FinalResponse:
        del wording_provider
        captured_non_answers.append(non_answer)
        return sentinel_response

    monkeypatch.setattr(
        workflow_runner.response_composer,
        "compose_non_answer_response",
        compose_non_answer_response,
    )
    return sentinel_response, captured_non_answers


def test_data_assistant_runs_end_to_end(
    canonical_question: str,
    connect_orders: local_duckdb_fixture.OrdersConnector,
    canonical_question_provider: question_interpreter.QuestionInterpreterProvider,
    allowed_internal_identity: contracts.InternalIdentity,
) -> None:
    order_rows = (
        ("2026-01-03", "North", "1200.00"),
        ("2026-01-08", "South", "850.00"),
        ("2026-01-15", "West", "1600.00"),
        ("2026-01-20", " ", "250.00"),
        ("2026-01-22", "North", "300.00"),
        ("2026-01-28", "East", "950.00"),
        ("2026-01-29", "East", None),
        ("2026-02-01", None, None),
    )
    with connect_orders(order_rows) as connection:
        run = workflow_runner.run_data_assistant(
            connection,
            canonical_question,
            question_interpreter_provider=canonical_question_provider,
            internal_identity=allowed_internal_identity,
        )

    assert isinstance(run, contracts.DataAssistantRun)
    assert run.question_frame.unresolved_ambiguities == ()
    assert run.available_data_resolution.resolved_match.table.table_id == "orders"
    assert len(run.available_data_resolution.dataset_selection.selected_datasets) == 1
    assert run.data_request.metric.label == "total revenue"
    assert run.prepared_data.data.loc[0, "dimension_value"] == "West"
    assert run.prepared_data.quality_notes == (
        "1 row excluded because revenue was missing.",
        "1 row grouped under Unknown because region was missing.",
    )
    assert "- Unknown: $250.00" in run.final_response.text
    assert "$5,150.00" in run.final_response.text
    assert run.final_response.response_kind == contracts.ResponseKind.ANSWER
    assert run.final_response.trust_summary.freshness == (
        "Commerce order data refreshed through 2026-01-31."
    )
    assert run.final_response.trust_summary.caveats == (
        "1 row excluded because revenue was missing.",
        "1 row grouped under Unknown because region was missing.",
    )
    assert "Trust Summary:" in run.final_response.text


def test_data_assistant_emits_staged_progress_in_order_on_happy_path(
    canonical_question: str,
    connect_orders: local_duckdb_fixture.OrdersConnector,
    canonical_question_provider: question_interpreter.QuestionInterpreterProvider,
    allowed_internal_identity: contracts.InternalIdentity,
) -> None:
    seen_statuses: list[str] = []

    with connect_orders((("2026-01-03", "North", "1200.00"),)) as connection:
        run = workflow_runner.run_data_assistant(
            connection,
            canonical_question,
            question_interpreter_provider=canonical_question_provider,
            internal_identity=allowed_internal_identity,
            progress_sink=seen_statuses.append,
        )

    assert isinstance(run, contracts.DataAssistantRun)
    assert seen_statuses == EXPECTED_PROGRESS_STATUSES


def test_data_assistant_answers_empty_commerce_q4_result_without_crashing(
    connect_orders: local_duckdb_fixture.OrdersConnector,
    allowed_internal_identity: contracts.InternalIdentity,
) -> None:
    provider = _static_provider(
        question_interpreter.QuestionFrameProposal(
            intent="summarize",
            metric="total revenue",
            field_operations=(
                question_interpreter.GroupByOperationProposal(
                    operation="group_by",
                    field="region",
                ),
                question_interpreter.RangeFilterOperationProposal(
                    operation="range_filter",
                    field="order date",
                    lower="2025-10-01",
                    upper="2025-12-31",
                ),
            ),
        )
    )
    order_rows = (
        ("2026-01-03", "North", "1200.00"),
        ("2026-01-08", "South", "850.00"),
    )

    with connect_orders(order_rows) as connection:
        run = workflow_runner.run_data_assistant(
            connection,
            "What was total revenue by region in Q4 2025?",
            question_interpreter_provider=provider,
            internal_identity=allowed_internal_identity,
        )

    assert isinstance(run, contracts.DataAssistantRun)
    assert run.prepared_data.data.empty
    assert run.answer_draft.summary == "No data was returned for this query."
    assert run.answer_draft.caveats == ("No rows matched the request filters.",)
    assert run.final_response.response_kind == contracts.ResponseKind.ANSWER
    assert "No data was returned for this query." in run.final_response.text
    assert "$0.00" not in run.final_response.text
    assert "0 regions" not in run.final_response.text
    assert "Time range: 2025-10-01 through 2025-12-31." in run.final_response.text
    assert "Caveats: No rows matched the request filters." in run.final_response.text
    assert "- North:" not in run.final_response.text


def test_data_assistant_runs_customer_count_by_customer_region_end_to_end(
    allowed_internal_identity: contracts.InternalIdentity,
) -> None:
    customer_rows = (
        ("2026-01-03", "cust-001", "North"),
        ("2026-01-08", "cust-002", "South"),
        ("2026-01-15", "cust-003", "North"),
        ("2026-01-22", "cust-004", "East"),
        ("2026-01-28", "cust-005", None),
        ("2026-02-01", "cust-006", "West"),
    )
    provider = _static_provider(
        question_interpreter.QuestionFrameProposal(
            intent="summarize",
            metric="customer count",
            field_operations=(
                question_interpreter.GroupByOperationProposal(
                    operation="group_by",
                    field="customer region",
                ),
                question_interpreter.RangeFilterOperationProposal(
                    operation="range_filter",
                    field="created date",
                    lower="2026-01-01",
                    upper="2026-01-31",
                ),
            ),
        )
    )

    with local_duckdb_fixture.connect_tables(
        (
            local_duckdb_fixture.orders_table_spec(()),
            local_duckdb_fixture.TableSpec(
                name="customers",
                columns=(
                    ("created_date", "date"),
                    ("customer_id", "varchar"),
                    ("customer_region", "varchar"),
                ),
                rows=customer_rows,
            ),
        )
    ) as connection:
        run = workflow_runner.run_data_assistant(
            connection,
            "What was customer count by customer region in January 2026?",
            question_interpreter_provider=provider,
            internal_identity=allowed_internal_identity,
        )

    assert isinstance(run, contracts.DataAssistantRun)
    assert run.available_data_resolution.resolved_match.table.table_id == "customers"
    assert run.data_request.metric.label == "customer count"
    assert run.prepared_data.quality_notes == (
        "1 row grouped under Unknown because customer region was missing.",
    )
    assert "Customer count in 2026-01-01 through 2026-01-31 was 5" in (
        run.final_response.text
    )
    assert "- North: 2" in run.final_response.text
    assert "- East: 1" in run.final_response.text
    assert "- South: 1" in run.final_response.text
    assert "- Unknown: 1" in run.final_response.text
    assert "$" not in run.final_response.text
    assert "Dataset Table: customers." in run.final_response.text
    assert "Time range: 2026-01-01 through 2026-01-31." in run.final_response.text
    assert "1 row grouped under Unknown because customer region was missing." in (
        run.final_response.text
    )


def test_data_assistant_runs_all_time_grouped_revenue_end_to_end(
    allowed_internal_identity: contracts.InternalIdentity,
) -> None:
    provider = _static_provider(
        question_interpreter.QuestionFrameProposal(
            intent="summarize",
            metric="total revenue",
            field_operations=(
                question_interpreter.GroupByOperationProposal(
                    operation="group_by",
                    field="region",
                ),
            ),
            all_time=True,
        )
    )
    order_rows = (
        ("2026-01-03", "North", "1200.00"),
        ("2026-01-08", "South", "850.00"),
        ("2026-01-15", "West", "1600.00"),
        ("2026-01-22", "North", "300.00"),
        ("2026-02-01", "West", "9999.00"),
    )

    with local_duckdb_fixture.connect_orders(order_rows) as connection:
        run = workflow_runner.run_data_assistant(
            connection,
            "What was total revenue by region for all time?",
            question_interpreter_provider=provider,
            internal_identity=allowed_internal_identity,
        )

    assert isinstance(run, contracts.DataAssistantRun)
    assert run.question_frame.time_scope == contracts.TimeScope.ALL_TIME
    assert run.data_request.filter_operations == ()
    assert run.prepared_data.data.loc[0, "dimension_value"] == "West"
    assert run.prepared_data.data.loc[0, "metric_value"] == 11599.0
    assert run.final_response.response_kind == contracts.ResponseKind.ANSWER
    assert "Total revenue in all available data was $13,949.00" in (
        run.final_response.text
    )
    assert "Time range: all available data." in run.final_response.text
    assert (
        run.final_response.trust_summary.freshness
        == "Commerce order data refreshed through 2026-01-31."
    )
    assert (
        "Freshness: Commerce order data refreshed through 2026-01-31."
        in run.final_response.text
    )
    assert "Filters:" not in run.final_response.text


def test_data_assistant_runs_all_time_scalar_revenue_end_to_end(
    allowed_internal_identity: contracts.InternalIdentity,
) -> None:
    provider = _static_provider(
        question_interpreter.QuestionFrameProposal(
            intent="summarize",
            metric="total revenue",
            field_operations=(),
            all_time=True,
        )
    )
    order_rows = (
        ("2026-01-03", "North", "1200.00"),
        ("2026-01-08", "South", "850.00"),
        ("2026-01-22", "North", "300.00"),
        ("2026-02-01", "West", "9999.00"),
    )

    with local_duckdb_fixture.connect_orders(order_rows) as connection:
        run = workflow_runner.run_data_assistant(
            connection,
            "What was total revenue for all time?",
            question_interpreter_provider=provider,
            internal_identity=allowed_internal_identity,
        )

    assert isinstance(run, contracts.DataAssistantRun)
    assert run.question_frame.time_scope == contracts.TimeScope.ALL_TIME
    assert run.data_request.filter_operations == ()
    assert run.prepared_data.data.loc[0, "dimension_value"] == "All"
    assert run.prepared_data.data.loc[0, "metric_value"] == 12349.0
    assert run.final_response.response_kind == contracts.ResponseKind.ANSWER
    assert "Total revenue in all available data was $12,349.00." in (
        run.final_response.text
    )
    assert "Time range: all available data." in run.final_response.text
    assert (
        run.final_response.trust_summary.freshness
        == "Commerce order data refreshed through 2026-01-31."
    )
    assert (
        "Freshness: Commerce order data refreshed through 2026-01-31."
        in run.final_response.text
    )
    assert "Filters:" not in run.final_response.text


@pytest.mark.parametrize(
    ("region_value", "expected_total", "question"),
    [
        (
            "North",
            1200.0,
            "What was total revenue in the North region for all time?",
        ),
        (
            "West",
            9999.0,
            "What was total revenue in the West region for all time?",
        ),
    ],
)
def test_data_assistant_runs_all_time_scalar_revenue_with_dimension_value_filter(
    allowed_internal_identity: contracts.InternalIdentity,
    region_value: str,
    expected_total: float,
    question: str,
) -> None:
    provider = _static_provider(
        question_interpreter.QuestionFrameProposal(
            intent="summarize",
            metric="total revenue",
            field_operations=(
                question_interpreter.IncludeFilterOperationProposal(
                    operation="include_filter",
                    field="region",
                    values=(region_value,),
                ),
            ),
            all_time=True,
        )
    )
    order_rows = (
        ("2026-01-03", "North", "1200.00"),
        ("2026-01-08", "South", "850.00"),
        ("2026-02-01", "West", "9999.00"),
    )

    with local_duckdb_fixture.connect_orders(order_rows) as connection:
        run = workflow_runner.run_data_assistant(
            connection,
            question,
            question_interpreter_provider=provider,
            internal_identity=allowed_internal_identity,
        )

    assert isinstance(run, contracts.DataAssistantRun)
    assert run.question_frame.time_scope == contracts.TimeScope.ALL_TIME
    assert run.question_frame.field_operations == (
        contracts.SemanticFieldOperation(
            operation=schema.FieldOperation.INCLUDE_FILTER,
            field="region",
            values=(region_value,),
        ),
    )
    assert run.data_request.group_by_fields == ()
    assert run.data_request.filter_labels == (f"region in ({region_value})",)
    assert run.prepared_data.data.loc[0, "dimension_value"] == "All"
    assert run.prepared_data.data.loc[0, "metric_value"] == expected_total
    formatted_total = f"${expected_total:,.2f}"
    assert f"Total revenue in all available data was {formatted_total}." in (
        run.final_response.text
    )
    assert f"Filters: region in ({region_value})." in run.final_response.text
    assert "- South:" not in run.final_response.text


def test_data_assistant_uses_supplied_reasoning_provider_for_final_narrative(
    allowed_internal_identity: contracts.InternalIdentity,
) -> None:
    provider = _static_provider(
        question_interpreter.QuestionFrameProposal(
            intent="summarize",
            metric="total revenue",
            field_operations=(
                question_interpreter.GroupByOperationProposal(
                    operation="group_by",
                    field="region",
                ),
                question_interpreter.RangeFilterOperationProposal(
                    operation="range_filter",
                    field="order date",
                    lower="2026-01-01",
                    upper="2026-01-31",
                ),
            ),
        )
    )
    reasoning_provider = reasoning_test_support.fixed_narrative_provider(
        reasoning_test_support.narrative_proposal(
            summary=(
                "{metric} in {time_range} stretched across {dimension_count} "
                "{dimension}, with {top_dimension} out front at {top_value}."
            )
        )
    )

    with local_duckdb_fixture.connect_orders(
        (
            ("2026-01-03", "North", "1200.00"),
            ("2026-01-08", "South", "850.00"),
            ("2026-01-15", "West", "1600.00"),
            ("2026-01-22", "North", "300.00"),
        )
    ) as connection:
        run = workflow_runner.run_data_assistant(
            connection,
            "What was total revenue by region in January 2026?",
            question_interpreter_provider=provider,
            reasoning_provider=reasoning_provider,
            internal_identity=allowed_internal_identity,
        )

    assert isinstance(run, contracts.DataAssistantRun)
    assert (
        run.answer_draft.summary
        == "Total revenue in 2026-01-01 through 2026-01-31 stretched across 3 "
        "regions, with West out front at $1,600.00."
    )
    assert (
        "Total revenue in 2026-01-01 through 2026-01-31 stretched across 3 "
        "regions, with West out front at $1,600.00." in run.final_response.text
    )
    assert reasoning_layer.WITHHELD_WORDING_CAVEAT not in run.answer_draft.caveats


def test_data_assistant_degrades_to_floor_when_reasoning_proposal_contains_digits(
    allowed_internal_identity: contracts.InternalIdentity,
) -> None:
    provider = _static_provider(
        question_interpreter.QuestionFrameProposal(
            intent="summarize",
            metric="total revenue",
            field_operations=(
                question_interpreter.GroupByOperationProposal(
                    operation="group_by",
                    field="region",
                ),
                question_interpreter.RangeFilterOperationProposal(
                    operation="range_filter",
                    field="order date",
                    lower="2026-01-01",
                    upper="2026-01-31",
                ),
            ),
        )
    )
    reasoning_provider = reasoning_test_support.fixed_narrative_provider(
        reasoning_layer.NarrativeProposal(
            summary="{metric} in {time_range} had 3 standout regions."
        )
    )

    with local_duckdb_fixture.connect_orders(
        (
            ("2026-01-03", "North", "1200.00"),
            ("2026-01-08", "South", "850.00"),
            ("2026-01-15", "West", "1600.00"),
            ("2026-01-22", "North", "300.00"),
        )
    ) as connection:
        run = workflow_runner.run_data_assistant(
            connection,
            "What was total revenue by region in January 2026?",
            question_interpreter_provider=provider,
            reasoning_provider=reasoning_provider,
            internal_identity=allowed_internal_identity,
        )

    assert isinstance(run, contracts.DataAssistantRun)
    assert (
        run.answer_draft.summary
        == "Total revenue in 2026-01-01 through 2026-01-31 was $3,950.00, "
        "grouped across 3 regions."
    )
    assert run.answer_draft.caveats == (reasoning_layer.WITHHELD_WORDING_CAVEAT,)
    assert run.final_response.trust_summary.caveats == (
        reasoning_layer.WITHHELD_WORDING_CAVEAT,
    )
    assert (
        "Caveats: Phrased from a standard template; generated wording was "
        "withheld." in run.final_response.text
    )


def test_data_assistant_short_circuits_question_ambiguity(
    monkeypatch: pytest.MonkeyPatch,
    connect_orders: local_duckdb_fixture.OrdersConnector,
    missing_time_scope_provider: question_interpreter.QuestionInterpreterProvider,
    allowed_internal_identity: contracts.InternalIdentity,
) -> None:
    sentinel_response, captured_non_answers = capture_non_answer_response(monkeypatch)
    order_rows = (("2026-01-03", "North", "1200.00"),)
    with connect_orders(order_rows) as connection:
        result = workflow_runner.run_data_assistant(
            connection,
            "What was total revenue by region?",
            question_interpreter_provider=missing_time_scope_provider,
            internal_identity=allowed_internal_identity,
        )

    assert result is sentinel_response
    assert len(captured_non_answers) == 1
    non_answer = captured_non_answers[0]
    assert non_answer.stage == contracts.NonAnswerStage.QUESTION_INTERPRETER
    assert non_answer.reason_code == contracts.NonAnswerReasonCode.MISSING_TIME_SCOPE


def test_data_assistant_stops_progress_after_question_interpreter_non_answer(
    monkeypatch: pytest.MonkeyPatch,
    connect_orders: local_duckdb_fixture.OrdersConnector,
    missing_time_scope_provider: question_interpreter.QuestionInterpreterProvider,
    allowed_internal_identity: contracts.InternalIdentity,
) -> None:
    sentinel_response, captured_non_answers = capture_non_answer_response(monkeypatch)
    seen_statuses: list[str] = []

    with connect_orders((("2026-01-03", "North", "1200.00"),)) as connection:
        result = workflow_runner.run_data_assistant(
            connection,
            "What was total revenue by region?",
            question_interpreter_provider=missing_time_scope_provider,
            internal_identity=allowed_internal_identity,
            progress_sink=seen_statuses.append,
        )

    assert result is sentinel_response
    assert seen_statuses == [EXPECTED_PROGRESS_STATUSES[0]]
    assert len(captured_non_answers) == 1
    assert (
        captured_non_answers[0].stage == contracts.NonAnswerStage.QUESTION_INTERPRETER
    )
    assert (
        captured_non_answers[0].reason_code
        == contracts.NonAnswerReasonCode.MISSING_TIME_SCOPE
    )


def test_data_assistant_rejects_rank_intent_before_provider_call(
    monkeypatch: pytest.MonkeyPatch,
    connect_orders: local_duckdb_fixture.OrdersConnector,
    allowed_internal_identity: contracts.InternalIdentity,
) -> None:
    sentinel_response, captured_non_answers = capture_non_answer_response(monkeypatch)

    class ProviderThatMustNotBeCalled:
        def propose_question_frame(
            self,
            *,
            question: str,
            semantic_layer_context: dict[str, object],
        ) -> question_interpreter.QuestionFrameProposal:
            del question, semantic_layer_context
            raise AssertionError("rank intent guard should short-circuit provider")

    with connect_orders((("2026-01-03", "North", "1200.00"),)) as connection:
        result = workflow_runner.run_data_assistant(
            connection,
            "Which region had the highest total revenue in January 2026?",
            question_interpreter_provider=ProviderThatMustNotBeCalled(),
            internal_identity=allowed_internal_identity,
        )

    assert result is sentinel_response
    assert len(captured_non_answers) == 1
    non_answer = captured_non_answers[0]
    assert non_answer.stage == contracts.NonAnswerStage.QUESTION_INTERPRETER
    assert non_answer.reason_code == contracts.NonAnswerReasonCode.UNSUPPORTED_INTENT


def test_data_assistant_rejects_availability_question_before_provider_call(
    monkeypatch: pytest.MonkeyPatch,
    connect_orders: local_duckdb_fixture.OrdersConnector,
    allowed_internal_identity: contracts.InternalIdentity,
) -> None:
    sentinel_response, captured_non_answers = capture_non_answer_response(monkeypatch)

    class ProviderThatMustNotBeCalled:
        def propose_question_frame(
            self,
            *,
            question: str,
            semantic_layer_context: dict[str, object],
        ) -> question_interpreter.QuestionFrameProposal:
            del question, semantic_layer_context
            raise AssertionError(
                "availability guard should short-circuit provider"
            )

    with connect_orders((("2026-01-03", "North", "1200.00"),)) as connection:
        result = workflow_runner.run_data_assistant(
            connection,
            "What months do have revenue data?",
            question_interpreter_provider=ProviderThatMustNotBeCalled(),
            internal_identity=allowed_internal_identity,
        )

    assert result is sentinel_response
    assert len(captured_non_answers) == 1
    non_answer = captured_non_answers[0]
    assert non_answer.stage == contracts.NonAnswerStage.QUESTION_INTERPRETER
    assert (
        non_answer.reason_code
        == contracts.NonAnswerReasonCode.UNSUPPORTED_AVAILABILITY
    )
    # The honest availability reject must not masquerade as a clarification.
    assert (
        non_answer.reason_code
        != contracts.NonAnswerReasonCode.MISSING_REQUIRED_FIELD
    )


def test_data_assistant_denies_dataset_access_before_request_or_preparation(
    monkeypatch: pytest.MonkeyPatch,
    canonical_question: str,
    connect_orders: local_duckdb_fixture.OrdersConnector,
    canonical_question_provider: question_interpreter.QuestionInterpreterProvider,
) -> None:
    sentinel_response, captured_non_answers = capture_non_answer_response(monkeypatch)

    def fail_create_data_request(
        question_frame: contracts.QuestionFrame,
        resolved_match: contracts.SemanticMatch,
    ) -> contracts.StageResult[contracts.DataRequest]:
        del question_frame, resolved_match
        raise AssertionError("create_data_request should not be called")

    def fail_prepare_data(
        data_request: contracts.DataRequest,
        connection: object,
    ) -> contracts.PreparedData:
        del data_request, connection
        raise AssertionError("prepare_data should not be called")

    monkeypatch.setattr(data_requester, "create_data_request", fail_create_data_request)
    monkeypatch.setattr(data_preparation, "prepare_data", fail_prepare_data)
    order_rows = (("2026-01-03", "North", "1200.00"),)

    with connect_orders(order_rows) as connection:
        result = workflow_runner.run_data_assistant(
            connection,
            canonical_question,
            question_interpreter_provider=canonical_question_provider,
            internal_identity=contracts.InternalIdentity(identity_id="employee_999"),
        )

    assert result is sentinel_response
    assert len(captured_non_answers) == 1
    non_answer = captured_non_answers[0]
    assert non_answer.stage == contracts.NonAnswerStage.ACCESS_CONTROLLER
    assert non_answer.reason_code == contracts.NonAnswerReasonCode.ACCESS_DENIED
    assert non_answer.datasets == ("commerce",)


def test_data_assistant_stops_progress_after_prepare_stage_non_answer(
    monkeypatch: pytest.MonkeyPatch,
    canonical_question: str,
    connect_orders: local_duckdb_fixture.OrdersConnector,
    canonical_question_provider: question_interpreter.QuestionInterpreterProvider,
    allowed_internal_identity: contracts.InternalIdentity,
) -> None:
    sentinel_response, captured_non_answers = capture_non_answer_response(monkeypatch)
    seen_statuses: list[str] = []

    def return_prepare_stage_non_answer(
        question_frame: contracts.QuestionFrame,
        resolved_match: contracts.SemanticMatch,
    ) -> contracts.StageResult[contracts.DataRequest]:
        del question_frame, resolved_match
        return contracts.NonAnswer(
            stage=contracts.NonAnswerStage.SEMANTIC_ROUTER,
            reason_code=contracts.NonAnswerReasonCode.NO_MATCHING_TABLE,
        )

    monkeypatch.setattr(
        data_requester,
        "create_data_request",
        return_prepare_stage_non_answer,
    )

    with connect_orders((("2026-01-03", "North", "1200.00"),)) as connection:
        result = workflow_runner.run_data_assistant(
            connection,
            canonical_question,
            question_interpreter_provider=canonical_question_provider,
            internal_identity=allowed_internal_identity,
            progress_sink=seen_statuses.append,
        )

    assert result is sentinel_response
    assert seen_statuses == EXPECTED_PROGRESS_STATUSES[:3]
    assert len(captured_non_answers) == 1
    assert (
        captured_non_answers[0].reason_code
        == contracts.NonAnswerReasonCode.NO_MATCHING_TABLE
    )


def test_data_assistant_returns_ambiguous_table_before_access_denial(
    monkeypatch: pytest.MonkeyPatch,
    connect_orders: local_duckdb_fixture.OrdersConnector,
) -> None:
    sentinel_response, captured_non_answers = capture_non_answer_response(monkeypatch)
    semantic_layer = _ambiguous_table_semantic_layer(
        allowed_identity_ids=("finance-team",),
    )
    provider = _static_provider(
        question_interpreter.QuestionFrameProposal(
            intent="summarize",
            metric="total revenue",
            field_operations=(
                question_interpreter.GroupByOperationProposal(
                    operation="group_by",
                    field="region",
                ),
            ),
            all_time=True,
        )
    )

    with connect_orders((("2026-01-03", "North", "1200.00"),)) as connection:
        result = workflow_runner.run_data_assistant(
            connection,
            "What was total revenue by region for all time?",
            question_interpreter_provider=provider,
            internal_identity=contracts.InternalIdentity(identity_id="employee_999"),
            semantic_layer=semantic_layer,
        )

    assert result is sentinel_response
    assert len(captured_non_answers) == 1
    non_answer = captured_non_answers[0]
    assert non_answer.stage == contracts.NonAnswerStage.SEMANTIC_ROUTER
    assert non_answer.reason_code == contracts.NonAnswerReasonCode.AMBIGUOUS_TABLE


def test_data_assistant_short_circuits_unsupported_question_before_preparing_data(
    monkeypatch: pytest.MonkeyPatch,
    connect_orders: local_duckdb_fixture.OrdersConnector,
    canonical_question_provider: question_interpreter.QuestionInterpreterProvider,
    allowed_internal_identity: contracts.InternalIdentity,
) -> None:
    sentinel_response, captured_non_answers = capture_non_answer_response(monkeypatch)

    def fail_prepare_data(
        data_request: contracts.DataRequest,
        connection: object,
    ) -> contracts.PreparedData:
        raise AssertionError("prepare_data should not be called")

    monkeypatch.setattr(data_preparation, "prepare_data", fail_prepare_data)
    order_rows = (("2026-01-03", "North", "1200.00"),)

    with connect_orders(order_rows) as connection:
        result = workflow_runner.run_data_assistant(
            connection,
            "Can you use my CSV file to show total revenue by region in January 2026?",
            question_interpreter_provider=canonical_question_provider,
            internal_identity=allowed_internal_identity,
        )

    assert result is sentinel_response
    assert len(captured_non_answers) == 1
    non_answer = captured_non_answers[0]
    assert non_answer.stage == contracts.NonAnswerStage.QUESTION_INTERPRETER
    assert non_answer.context == ("unsupported data",)
    assert non_answer.datasets == ()


def test_data_assistant_uses_required_question_interpreter_provider(
    canonical_question: str,
    connect_orders: local_duckdb_fixture.OrdersConnector,
    allowed_internal_identity: contracts.InternalIdentity,
) -> None:
    class FakeProvider:
        def propose_question_frame(
            self,
            *,
            question: str,
            semantic_layer_context: dict[str, object],
        ) -> question_interpreter.QuestionFrameProposal:
            assert question == canonical_question
            assert "all_metric_labels" in semantic_layer_context
            return question_interpreter.QuestionFrameProposal(
                intent="summarize",
                metric="total revenue",
                field_operations=(
                    question_interpreter.GroupByOperationProposal(
                        operation="group_by",
                        field="region",
                    ),
                    question_interpreter.RangeFilterOperationProposal(
                        operation="range_filter",
                        field="order date",
                        lower="2026-01-01",
                        upper="2026-01-31",
                    ),
                ),
            )

    with connect_orders((("2026-01-03", "North", "1200.00"),)) as connection:
        run = workflow_runner.run_data_assistant(
            connection,
            canonical_question,
            question_interpreter_provider=FakeProvider(),
            internal_identity=allowed_internal_identity,
        )

    assert isinstance(run, contracts.DataAssistantRun)
    assert run.question_frame == contracts.QuestionFrame(
        intent="summarize",
        metric="total revenue",
        time_scope=contracts.TimeScope.BOUNDED,
        field_operations=(
            contracts.SemanticFieldOperation(
                operation=schema.FieldOperation.GROUP_BY,
                field="region",
            ),
            contracts.SemanticFieldOperation(
                operation=schema.FieldOperation.RANGE_FILTER,
                field="order date",
                lower=datetime.date(2026, 1, 1),
                upper=datetime.date(2026, 1, 31),
            ),
        ),
        unresolved_ambiguities=(),
    )


def _ambiguous_table_semantic_layer(
    *,
    allowed_identity_ids: tuple[str, ...],
) -> schema.SemanticLayer:
    freshness = schema.Freshness(
        as_of=datetime.date(2026, 1, 31),
        description="Clean fixture rows for January 2026.",
    )
    dataset = schema.CuratedDataset(
        dataset_id="commerce",
        name="Commerce",
        tables=("orders", "order_rollups"),
        information_types=("revenue",),
        freshness=freshness,
        example_questions=(),
        dataset_access=schema.DatasetAccess(
            allowed_identity_ids=allowed_identity_ids,
        ),
    )
    metric = schema.Metric(
        metric_id="total_revenue",
        label="total revenue",
        expression="sum(revenue)",
        source_column="revenue",
        kind=schema.MetricKind.MONEY,
    )
    field = schema.SemanticField(
        field_id="region",
        label="region",
        source_column="region",
        data_type=schema.DataType.STRING,
        operations=(schema.FieldOperation.GROUP_BY,),
    )
    return schema.SemanticLayer(
        datasets=(dataset,),
        tables=(
            _table("orders", metric, field),
            _table("order_rollups", metric, field),
        ),
    )


def _static_provider(
    proposal: question_interpreter.QuestionFrameProposal,
) -> question_interpreter.QuestionInterpreterProvider:
    class StaticProvider:
        def propose_question_frame(
            self,
            *,
            question: str,
            semantic_layer_context: dict[str, object],
        ) -> question_interpreter.QuestionFrameProposal:
            del question, semantic_layer_context
            return proposal

    return StaticProvider()


def _table(
    table_id: str,
    metric: schema.Metric,
    field: schema.SemanticField,
) -> schema.DatasetTable:
    return schema.DatasetTable(
        table_id=table_id,
        dataset_id="commerce",
        description="Test table.",
        columns=(
            schema.TableColumn(column_id="order_date", data_type="date"),
            schema.TableColumn(column_id="region", data_type="string"),
            schema.TableColumn(column_id="revenue", data_type="decimal"),
        ),
        metrics=(metric,),
        fields=(field,),
    )

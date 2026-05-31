import datetime

import pytest

import data_assistant.data_preparation as data_preparation
import data_assistant.data_requester as data_requester
import data_assistant.local_orders_fixture as local_orders_fixture
import data_assistant.question_interpreter as question_interpreter
import data_assistant.semantic_layer.schema as schema
import data_assistant.workflow.contracts as contracts
import data_assistant.workflow.runner as workflow_runner


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
    connect_orders: local_orders_fixture.OrdersConnector,
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
    assert (
        len(run.available_data_resolution.dataset_selection.selected_datasets)
        == 1
    )
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


def test_data_assistant_short_circuits_question_ambiguity(
    monkeypatch: pytest.MonkeyPatch,
    connect_orders: local_orders_fixture.OrdersConnector,
    missing_time_range_provider: question_interpreter.QuestionInterpreterProvider,
    allowed_internal_identity: contracts.InternalIdentity,
) -> None:
    sentinel_response, captured_non_answers = capture_non_answer_response(monkeypatch)
    order_rows = (
        ("2026-01-03", "North", "1200.00"),
    )
    with connect_orders(order_rows) as connection:
        result = workflow_runner.run_data_assistant(
            connection,
            "What was total revenue by region?",
            question_interpreter_provider=missing_time_range_provider,
            internal_identity=allowed_internal_identity,
        )

    assert result is sentinel_response
    assert len(captured_non_answers) == 1
    non_answer = captured_non_answers[0]
    assert non_answer.stage == contracts.NonAnswerStage.QUESTION_INTERPRETER
    assert non_answer.context == ("metric",)


def test_data_assistant_denies_dataset_access_before_request_or_preparation(
    monkeypatch: pytest.MonkeyPatch,
    canonical_question: str,
    connect_orders: local_orders_fixture.OrdersConnector,
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


def test_data_assistant_returns_ambiguous_table_before_access_denial(
    monkeypatch: pytest.MonkeyPatch,
    connect_orders: local_orders_fixture.OrdersConnector,
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
        )
    )

    with connect_orders((("2026-01-03", "North", "1200.00"),)) as connection:
        result = workflow_runner.run_data_assistant(
            connection,
            "What was total revenue by region?",
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
    connect_orders: local_orders_fixture.OrdersConnector,
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
    order_rows = (
        ("2026-01-03", "North", "1200.00"),
    )

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
    connect_orders: local_orders_fixture.OrdersConnector,
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
        name="Commerce Revenue",
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

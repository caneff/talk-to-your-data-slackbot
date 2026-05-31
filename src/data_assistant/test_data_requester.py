import datetime

import data_assistant.data_requester as data_requester
import data_assistant.semantic_layer.schema as schema
import data_assistant.workflow.contracts as contracts


def test_data_request_asks_for_total_revenue_grouped_by_region(
    data_request: contracts.DataRequest,
) -> None:
    assert data_request.dataset.dataset_id == "commerce"
    assert data_request.table.table_id == "orders"
    assert data_request.metric.metric_id == "total_revenue"
    assert data_request.metric.label == "total revenue"
    assert data_request.metric.expression == "sum(revenue)"
    assert data_request.metric.source_column == "revenue"
    assert data_request.group_by_fields[0].field_id == "region"
    assert data_request.group_by_fields[0].label == "region"
    assert data_request.group_by_fields[0].source_column == "region"
    assert data_request.table.date_column == "order_date"
    assert data_request.filter_labels == (
        "order date >= 2026-01-01 and <= 2026-01-31",
    )
    assert data_request.output_shape == "total revenue grouped by region"


def test_data_request_selects_orders_when_commerce_has_customer_metadata(
    data_request: contracts.DataRequest,
) -> None:
    assert data_request.dataset.tables == ("orders", "customers")
    assert data_request.table.table_id == "orders"
    assert data_request.metric.metric_id == "total_revenue"
    assert data_request.group_by_fields[0].field_id == "region"


def test_data_requester_returns_non_answer_for_ambiguous_tables() -> None:
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
        data_type="string",
        operations=(schema.FieldOperation.GROUP_BY,),
    )
    semantic_layer = schema.SemanticLayer(
        datasets=(dataset,),
        tables=(
            _table("orders", metric, field),
            _table("order_rollups", metric, field),
        ),
    )
    question_frame = contracts.QuestionFrame(
        intent="summarize",
        metric="total revenue",
        field_operations=(
            contracts.SemanticFieldOperation(
                operation=contracts.FieldOperationKind.GROUP_BY,
                field="region",
            ),
        ),
        unresolved_ambiguities=(),
    )
    dataset_selection = contracts.DatasetSelection(
        selected_datasets=(dataset,),
        match_rationale="test",
    )
    semantic_matches = (
        contracts.SemanticMatch(
            dataset=dataset,
            table=semantic_layer.tables[0],
            metric=metric,
            group_by_fields=(field,),
        ),
        contracts.SemanticMatch(
            dataset=dataset,
            table=semantic_layer.tables[1],
            metric=metric,
            group_by_fields=(field,),
        ),
    )

    result = data_requester.create_data_request(
        question_frame,
        dataset_selection,
        semantic_matches,
    )

    assert result == contracts.NonAnswer(
        stage=contracts.NonAnswerStage.DATA_REQUESTER,
        reason_code=contracts.NonAnswerReasonCode.AMBIGUOUS_TABLE,
        reason="Multiple Dataset Tables can satisfy the Question Frame.",
        unresolved_ambiguities=("dataset table",),
        next_step="Ask which Dataset Table should be used.",
    )


def test_data_requester_returns_non_answer_when_selection_has_no_table_match(
    question_frame: contracts.QuestionFrame,
    dataset_selection: contracts.DatasetSelection,
) -> None:
    result = data_requester.create_data_request(
        question_frame,
        dataset_selection,
        semantic_matches=(),
    )

    assert result == contracts.NonAnswer(
        stage=contracts.NonAnswerStage.DATA_REQUESTER,
        reason_code=contracts.NonAnswerReasonCode.NO_MATCHING_TABLE,
        reason="No Dataset Table can satisfy the Question Frame.",
        unresolved_ambiguities=("dataset table",),
        next_step="Ask which table-level metric or dimension should be used.",
    )


def _table(
    table_id: str,
    metric: schema.Metric,
    field: schema.SemanticField,
) -> schema.DatasetTable:
    return schema.DatasetTable(
        table_id=table_id,
        dataset_id="commerce",
        description="Test table.",
        date_column="order_date",
        columns=(
            schema.TableColumn(column_id="order_date", data_type="date"),
            schema.TableColumn(column_id="region", data_type="string"),
            schema.TableColumn(column_id="revenue", data_type="decimal"),
        ),
        metrics=(metric,),
        fields=(field,),
    )

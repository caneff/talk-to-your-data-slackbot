import data_assistant.non_answer_catalog as non_answer_catalog
import data_assistant.semantic_layer.catalog as semantic_layer_catalog
import data_assistant.semantic_layer.schema as schema
import data_assistant.semantic_matcher as semantic_matcher
import data_assistant.semantic_router as semantic_router
import data_assistant.workflow.contracts as contracts


def test_semantic_router_resolves_available_data(
    question_frame: contracts.QuestionFrame,
    active_semantic_layer: semantic_layer_catalog.SemanticLayerCatalog,
) -> None:
    result = semantic_router.resolve_available_data(
        question_frame,
        active_semantic_layer,
    )

    assert not isinstance(result, contracts.NonAnswer)
    resolution = result.value
    assert resolution.resolved_match.table.table_id == "orders"
    assert len(resolution.dataset_selection.selected_datasets) == 1
    assert resolution.dataset_selection.selected_datasets[0].dataset_id == "retail_ops"


def test_dataset_selection_chooses_one_curated_dataset_with_rationale(
    dataset_selection: contracts.DatasetSelection,
) -> None:
    assert len(dataset_selection.selected_datasets) == 1
    assert dataset_selection.selected_datasets[0].dataset_id == "retail_ops"
    assert "total revenue metric and region fields" in (
        dataset_selection.match_rationale
    )


def test_semantic_router_returns_non_answer_when_no_dataset_matches(
    active_semantic_layer: semantic_layer_catalog.SemanticLayerCatalog,
) -> None:
    question_frame = contracts.QuestionFrame(
        intent="summarize",
        metric="gross bookings",
        time_scope=contracts.TimeScope.BOUNDED,
        group_by_field="region",
        field_filters=(),
        unresolved_ambiguities=(),
    )
    semantic_matches = semantic_matcher.find_semantic_matches(
        question_frame,
        active_semantic_layer,
    )

    result = semantic_router.select_dataset(semantic_matches)

    assert result == non_answer_catalog.non_answer(
        contracts.NonAnswerReasonCode.NO_MATCHING_DATASET,
        stage=contracts.NonAnswerStage.SEMANTIC_ROUTER,
    )


def test_semantic_router_returns_ambiguous_table_for_two_tables_in_one_dataset() -> (
    None
):
    dataset = schema.CuratedDataset(
        dataset_id="retail_ops",
        name="Retail Operations",
        tables=("orders", "order_rollups"),
        information_types=("revenue",),
        example_questions=(),
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
    semantic_layer = semantic_layer_catalog.SemanticLayerCatalog(
        datasets=(dataset,),
        tables=(
            _table("orders", metric, field),
            _table("order_rollups", metric, field),
        ),
    )
    question_frame = contracts.QuestionFrame(
        intent="summarize",
        metric="total revenue",
        time_scope=contracts.TimeScope.BOUNDED,
        group_by_field="region",
        field_filters=(),
        unresolved_ambiguities=(),
    )

    result = semantic_router.resolve_available_data(
        question_frame,
        semantic_layer,
    )

    assert result == non_answer_catalog.non_answer(
        contracts.NonAnswerReasonCode.AMBIGUOUS_TABLE,
        stage=contracts.NonAnswerStage.SEMANTIC_ROUTER,
    )


def test_resolve_semantic_match_returns_no_matching_table_from_router() -> None:
    selected_dataset = schema.CuratedDataset(
        dataset_id="retail_ops",
        name="Retail Operations",
        tables=("orders",),
        information_types=("revenue",),
        example_questions=(),
    )
    other_dataset = schema.CuratedDataset(
        dataset_id="support",
        name="Support Tickets",
        tables=("tickets",),
        information_types=("support",),
        example_questions=(),
    )
    metric = schema.Metric(
        metric_id="ticket_count",
        label="ticket count",
        expression="count(*)",
        source_column="ticket_id",
        kind=schema.MetricKind.COUNT,
    )
    field = schema.SemanticField(
        field_id="region",
        label="region",
        source_column="region",
        data_type=schema.DataType.STRING,
        operations=(schema.FieldOperation.GROUP_BY,),
    )
    semantic_matches = (
        contracts.SemanticMatch(
            dataset=other_dataset,
            table=schema.DatasetTable(
                table_id="tickets",
                dataset_id="support",
                description="Support table.",
                columns=(
                    schema.TableColumn(column_id="ticket_id", data_type="string"),
                    schema.TableColumn(column_id="region", data_type="string"),
                ),
                metrics=(metric,),
                fields=(field,),
            ),
            metric=metric,
            group_by_field=field,
            field_filters=(),
        ),
    )
    dataset_selection = contracts.DatasetSelection(
        selected_datasets=(selected_dataset,),
        match_rationale="test",
    )

    result = semantic_router.resolve_semantic_match(
        semantic_matches,
        dataset_selection,
    )

    assert result == non_answer_catalog.non_answer(
        contracts.NonAnswerReasonCode.NO_MATCHING_TABLE,
        stage=contracts.NonAnswerStage.SEMANTIC_ROUTER,
    )


def _table(
    table_id: str,
    metric: schema.Metric,
    field: schema.SemanticField,
) -> schema.DatasetTable:
    return schema.DatasetTable(
        table_id=table_id,
        dataset_id="retail_ops",
        description="Test table.",
        columns=(
            schema.TableColumn(column_id="order_date", data_type="date"),
            schema.TableColumn(column_id="region", data_type="string"),
            schema.TableColumn(column_id="revenue", data_type="decimal"),
        ),
        metrics=(metric,),
        fields=(field,),
    )

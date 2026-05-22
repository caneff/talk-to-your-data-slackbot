import datetime

from data_slackbot.clean_commerce_spine import query_planner
from data_slackbot.clean_commerce_spine.semantic_layer import schema
from data_slackbot.clean_commerce_spine.workflow import contracts


def test_data_request_asks_for_total_revenue_grouped_by_region(
    data_request: contracts.DataRequest,
) -> None:
    assert data_request.curated_dataset_id == "commerce"
    assert data_request.table_id == "orders"
    assert data_request.metric_id == "total_revenue"
    assert data_request.metric_label == "total revenue"
    assert data_request.metric_expression == "sum(revenue)"
    assert data_request.dimension_id == "region"
    assert data_request.dimension_label == "region"
    assert data_request.dimension_column == "region"
    assert data_request.date_column == "order_date"
    assert data_request.time_range.label == "January 2026"
    assert data_request.filters == ()
    assert data_request.output_shape == "total revenue grouped by region"


def test_query_planner_returns_non_answer_for_ambiguous_tables() -> None:
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
    )
    dimension = schema.Dimension(
        dimension_id="region",
        label="region",
        column="region",
    )
    semantic_layer = schema.SemanticLayer(
        datasets=(dataset,),
        tables=(
            _table("orders", metric, dimension),
            _table("order_rollups", metric, dimension),
        ),
    )
    question_frame = contracts.QuestionFrame(
        intent="summarize",
        metric="total revenue",
        dimension="region",
        time_range=contracts.TimeRange(
            label="January 2026",
            start_date=datetime.date(2026, 1, 1),
            end_date=datetime.date(2026, 1, 31),
        ),
        filters=(),
        unresolved_ambiguities=(),
    )
    dataset_selection = contracts.DatasetSelection(
        selected_datasets=(dataset,),
        match_rationale="test",
    )

    result = query_planner.create_data_request(
        question_frame,
        dataset_selection,
        semantic_layer,
    )

    assert result == contracts.NonAnswer(
        stage="query_planner",
        reason="Multiple Dataset Tables can satisfy the Question Frame.",
        unresolved_ambiguities=("dataset table",),
        next_step="Ask which Dataset Table should be used.",
    )


def _table(
    table_id: str,
    metric: schema.Metric,
    dimension: schema.Dimension,
) -> schema.DatasetTable:
    return schema.DatasetTable(
        table_id=table_id,
        dataset_id="commerce",
        description="Test table.",
        date_column="order_date",
        columns=(),
        metrics=(metric,),
        dimensions=(dimension,),
    )

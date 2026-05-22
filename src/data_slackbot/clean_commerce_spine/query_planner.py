"""Query Planner step for clean commerce Data Request creation."""

from __future__ import annotations

from data_slackbot.clean_commerce_spine import semantic_layer as semantic_layer_module
from data_slackbot.clean_commerce_spine.semantic_layer import schema
from data_slackbot.clean_commerce_spine.workflow import contracts


def create_data_request(
    question_frame: contracts.QuestionFrame,
    dataset_selection: contracts.DatasetSelection,
    semantic_layer: schema.SemanticLayer,
) -> contracts.StageResult[contracts.DataRequest]:
    """Create the Data Request for revenue grouped by region."""
    if len(dataset_selection.selected_datasets) != 1:
        return contracts.NonAnswer(
            stage="query_planner",
            reason="A Data Request requires exactly one Curated Dataset.",
            unresolved_ambiguities=("curated dataset",),
            next_step="Resolve dataset selection before planning retrieval.",
        )

    dataset = dataset_selection.selected_datasets[0]
    table_options = _table_options_for_question_frame(
        dataset, question_frame, semantic_layer
    )

    if not table_options:
        return contracts.NonAnswer(
            stage="query_planner",
            reason="No Dataset Table can satisfy the Question Frame.",
            unresolved_ambiguities=("dataset table",),
            next_step="Ask which table-level metric or dimension should be used.",
        )
    if len(table_options) > 1:
        return contracts.NonAnswer(
            stage="query_planner",
            reason="Multiple Dataset Tables can satisfy the Question Frame.",
            unresolved_ambiguities=("dataset table",),
            next_step="Ask which Dataset Table should be used.",
        )

    table, metric, dimension = next(iter(table_options))
    return contracts.Success(
        contracts.DataRequest(
            curated_dataset_id=dataset.dataset_id,
            table_id=table.table_id,
            metric_id=metric.metric_id,
            metric_label=metric.label,
            metric_expression=metric.expression,
            dimension_id=dimension.dimension_id,
            dimension_label=dimension.label,
            dimension_column=dimension.column,
            date_column=table.date_column,
            time_range=question_frame.time_range,
            filters=question_frame.filters,
            output_shape="total revenue grouped by region",
            result_limit=10,
        ),
    )


def _table_options_for_question_frame(
    dataset: schema.CuratedDataset,
    question_frame: contracts.QuestionFrame,
    semantic_layer: schema.SemanticLayer,
) -> tuple[tuple[schema.DatasetTable, schema.Metric, schema.Dimension], ...]:
    options: list[tuple[schema.DatasetTable, schema.Metric, schema.Dimension]] = []
    for table in semantic_layer_module.tables_for_dataset(dataset, semantic_layer):
        metric = _find_metric(question_frame.metric, table)
        dimension = _find_dimension(question_frame.dimension, table)
        if metric is not None and dimension is not None:
            options.append((table, metric, dimension))
    return tuple(options)


def _find_metric(metric_label: str, table: schema.DatasetTable) -> schema.Metric | None:
    return next(
        (metric for metric in table.metrics if metric.label == metric_label),
        None,
    )


def _find_dimension(
    dimension_label: str,
    table: schema.DatasetTable,
) -> schema.Dimension | None:
    return next(
        (
            dimension
            for dimension in table.dimensions
            if dimension.label == dimension_label
        ),
        None,
    )

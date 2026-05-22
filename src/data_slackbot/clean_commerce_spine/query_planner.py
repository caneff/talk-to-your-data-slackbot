"""Query Planner step for clean commerce Data Request creation."""

from __future__ import annotations

from data_slackbot.clean_commerce_spine import contracts
from data_slackbot.clean_commerce_spine import semantic_layer as semantic_layer_module


def create_data_request(
    question_frame: contracts.QuestionFrame,
    dataset_selection: contracts.DatasetSelection,
    semantic_layer: contracts.SemanticLayer,
) -> contracts.DataRequest:
    """Create the Data Request for revenue grouped by region."""
    if len(dataset_selection.selected_datasets) != 1:
        msg = "A clean Data Request requires exactly one Curated Dataset."
        raise ValueError(msg)

    dataset = dataset_selection.selected_datasets[0]
    table, metric, dimension = semantic_layer_module.find_table_for_question_frame(
        dataset,
        question_frame,
        semantic_layer,
    )
    return contracts.DataRequest(
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
    )

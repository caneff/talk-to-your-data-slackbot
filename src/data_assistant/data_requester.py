"""Data Requester step for Data Assistant Data Request creation."""

from __future__ import annotations

import data_assistant.semantic_layer.loader as semantic_layer_loader
import data_assistant.semantic_layer.schema as schema
import data_assistant.workflow.contracts as contracts

DEFAULT_RESULT_LIMIT = 10


def create_data_request(
    question_frame: contracts.QuestionFrame,
    dataset_selection: contracts.DatasetSelection,
    semantic_layer: schema.SemanticLayer,
) -> contracts.StageResult[contracts.DataRequest]:
    """Create the Data Request for revenue grouped by region."""
    if len(dataset_selection.selected_datasets) != 1:
        return contracts.NonAnswer(
            stage=contracts.NonAnswerStage.DATA_REQUESTER,
            reason_code=contracts.NonAnswerReasonCode.AMBIGUOUS_DATASET,
            reason="A Data Request requires exactly one Curated Dataset.",
            unresolved_ambiguities=("curated dataset",),
            next_step="Resolve dataset selection before planning retrieval.",
        )

    dataset = dataset_selection.selected_datasets[0]
    table_options: list[
        tuple[schema.DatasetTable, schema.Metric, schema.Dimension]
    ] = []
    for table in semantic_layer_loader.tables_for_dataset(dataset, semantic_layer):
        metric = next(
            (
                metric
                for metric in table.metrics
                if metric.label == question_frame.metric
            ),
            None,
        )
        dimension = next(
            (
                dimension
                for dimension in table.dimensions
                if dimension.label == question_frame.dimension
            ),
            None,
        )
        if metric is not None and dimension is not None:
            table_options.append((table, metric, dimension))

    if not table_options:
        return contracts.NonAnswer(
            stage=contracts.NonAnswerStage.DATA_REQUESTER,
            reason_code=contracts.NonAnswerReasonCode.NO_MATCHING_TABLE,
            reason="No Dataset Table can satisfy the Question Frame.",
            unresolved_ambiguities=("dataset table",),
            next_step="Ask which table-level metric or dimension should be used.",
        )
    if len(table_options) > 1:
        return contracts.NonAnswer(
            stage=contracts.NonAnswerStage.DATA_REQUESTER,
            reason_code=contracts.NonAnswerReasonCode.AMBIGUOUS_TABLE,
            reason="Multiple Dataset Tables can satisfy the Question Frame.",
            unresolved_ambiguities=("dataset table",),
            next_step="Ask which Dataset Table should be used.",
        )

    table, metric, dimension = table_options[0]
    return contracts.Success(
        contracts.DataRequest(
            dataset=dataset,
            table=table,
            metric=metric,
            dimension=dimension,
            time_range=question_frame.time_range,
            filters=question_frame.filters,
            output_shape=f"{metric.label} grouped by {dimension.label}",
            result_limit=DEFAULT_RESULT_LIMIT,
        ),
    )

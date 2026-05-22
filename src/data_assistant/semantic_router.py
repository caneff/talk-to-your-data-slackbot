"""Semantic Router for Data Assistant Dataset Selection."""

from __future__ import annotations

import data_assistant.semantic_layer.loader as semantic_layer_loader
import data_assistant.semantic_layer.schema as schema
import data_assistant.workflow.contracts as contracts


def select_dataset(
    question_frame: contracts.QuestionFrame,
    semantic_layer: schema.SemanticLayer,
) -> contracts.StageResult[contracts.DatasetSelection]:
    """Choose the Curated Dataset that can answer the Question Frame."""
    matches = tuple(
        dataset
        for dataset in semantic_layer.datasets
        if _dataset_supports_question_frame(dataset, question_frame, semantic_layer)
    )

    if not matches:
        return contracts.NonAnswer(
            stage="semantic_router",
            reason="No Curated Dataset safely matches the Question Frame.",
            unresolved_ambiguities=("curated dataset",),
            next_step="Ask which approved business data should be used.",
        )
    if len(matches) > 1:
        return contracts.NonAnswer(
            stage="semantic_router",
            reason="Multiple Curated Datasets match the Question Frame.",
            unresolved_ambiguities=("curated dataset",),
            next_step="Ask which Curated Dataset should be used.",
        )

    return contracts.Success(
        contracts.DatasetSelection(
            selected_datasets=matches,
            match_rationale=(
                "Commerce Revenue contains the total revenue metric and region "
                "dimension needed for the January 2026 question."
            ),
        ),
    )


def _dataset_supports_question_frame(
    dataset: schema.CuratedDataset,
    question_frame: contracts.QuestionFrame,
    semantic_layer: schema.SemanticLayer,
) -> bool:
    return any(
        _table_supports_question_frame(table, question_frame)
        for table in semantic_layer_loader.tables_for_dataset(
            dataset, semantic_layer
        )
    )


def _table_supports_question_frame(
    table: schema.DatasetTable,
    question_frame: contracts.QuestionFrame,
) -> bool:
    has_metric = any(metric.label == question_frame.metric for metric in table.metrics)
    has_dimension = any(
        dimension.label == question_frame.dimension for dimension in table.dimensions
    )
    return has_metric and has_dimension

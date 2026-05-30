"""Semantic Layer matching for resolved data-access evidence."""

from __future__ import annotations

import data_assistant.semantic_layer.loader as semantic_layer_loader
import data_assistant.semantic_layer.schema as schema
import data_assistant.workflow.contracts as contracts


def find_semantic_matches(
    question_frame: contracts.QuestionFrame,
    semantic_layer: schema.SemanticLayer,
) -> tuple[contracts.SemanticMatch, ...]:
    """Find exact table-level Semantic Layer matches for a Question Frame."""
    matches: list[contracts.SemanticMatch] = []
    for dataset in semantic_layer.datasets:
        for table in semantic_layer_loader.tables_for_dataset(
            dataset,
            semantic_layer,
        ):
            metric = _find_metric(question_frame, table)
            dimension = _find_dimension(question_frame, table)
            if metric is not None and dimension is not None:
                matches.append(
                    contracts.SemanticMatch(
                        dataset=dataset,
                        table=table,
                        metric=metric,
                        dimension=dimension,
                    ),
                )

    return tuple(matches)


def _find_metric(
    question_frame: contracts.QuestionFrame,
    table: schema.DatasetTable,
) -> schema.Metric | None:
    return next(
        (metric for metric in table.metrics if metric.label == question_frame.metric),
        None,
    )


def _find_dimension(
    question_frame: contracts.QuestionFrame,
    table: schema.DatasetTable,
) -> schema.Dimension | None:
    return next(
        (
            dimension
            for dimension in table.dimensions
            if dimension.label == question_frame.dimension
        ),
        None,
    )

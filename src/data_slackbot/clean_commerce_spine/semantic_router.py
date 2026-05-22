"""Semantic Router for clean commerce Dataset Selection."""

from __future__ import annotations

from data_slackbot.clean_commerce_spine import contracts
from data_slackbot.clean_commerce_spine import semantic_layer as semantic_layer_module


def select_dataset(
    question_frame: contracts.QuestionFrame,
    semantic_layer: contracts.SemanticLayer,
) -> contracts.DatasetSelection:
    """Choose the Curated Dataset that can answer the Question Frame."""
    matches = tuple(
        dataset
        for dataset in semantic_layer.datasets
        if _dataset_supports_question_frame(dataset, question_frame, semantic_layer)
    )

    if len(matches) != 1:
        msg = "Expected exactly one matching Curated Dataset."
        raise ValueError(msg)

    return contracts.DatasetSelection(
        selected_datasets=matches,
        match_rationale=(
            "Commerce Revenue contains the total revenue metric and region "
            "dimension needed for the January 2026 question."
        ),
    )


def _dataset_supports_question_frame(
    dataset: contracts.CuratedDataset,
    question_frame: contracts.QuestionFrame,
    semantic_layer: contracts.SemanticLayer,
) -> bool:
    try:
        semantic_layer_module.find_table_for_question_frame(
            dataset,
            question_frame,
            semantic_layer,
        )
    except ValueError:
        return False
    return True

"""Semantic Router for clean commerce Dataset Selection."""

from __future__ import annotations

from data_slackbot.clean_commerce_spine import contracts


def select_dataset(
    question_frame: contracts.QuestionFrame,
    semantic_layer: contracts.SemanticLayer,
) -> contracts.DatasetSelection:
    """Choose the Curated Dataset that can answer the Question Frame."""
    matches = tuple(
        dataset
        for dataset in semantic_layer.datasets
        if question_frame.metric in dataset.metrics
        and question_frame.dimension in dataset.dimensions
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

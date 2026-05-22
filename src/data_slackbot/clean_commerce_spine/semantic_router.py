"""Semantic Router for clean commerce Dataset Selection."""

from __future__ import annotations

from data_slackbot.clean_commerce_spine import semantic_layer as semantic_layer_module
from data_slackbot.clean_commerce_spine.semantic_layer import schema
from data_slackbot.clean_commerce_spine.workflow import contracts


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
    try:
        semantic_layer_module.find_table_for_question_frame(
            dataset,
            question_frame,
            semantic_layer,
        )
    except ValueError:
        return False
    return True

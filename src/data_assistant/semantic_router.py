"""Semantic Router for Data Assistant Dataset Selection."""

from __future__ import annotations

import data_assistant.non_answer_catalog as non_answer_catalog
import data_assistant.semantic_layer.schema as schema
import data_assistant.semantic_matcher as semantic_matcher
import data_assistant.workflow.contracts as contracts


def resolve_available_data(
    question_frame: contracts.QuestionFrame,
    semantic_layer: schema.SemanticLayer,
) -> contracts.StageResult[contracts.AvailableDataResolution]:
    """Resolve Available Data evidence and Dataset Selection."""
    semantic_matches = semantic_matcher.find_semantic_matches(
        question_frame=question_frame,
        semantic_layer=semantic_layer,
    )
    dataset_selection_result = select_dataset(semantic_matches)
    if isinstance(dataset_selection_result, contracts.NonAnswer):
        return dataset_selection_result

    return contracts.Success(
        contracts.AvailableDataResolution(
            semantic_matches=semantic_matches,
            dataset_selection=dataset_selection_result.value,
        ),
    )


def select_dataset(
    semantic_matches: tuple[contracts.SemanticMatch, ...],
) -> contracts.StageResult[contracts.DatasetSelection]:
    """Choose the Curated Dataset represented by Semantic Layer matches."""
    datasets_by_id = {
        match.dataset.dataset_id: match.dataset for match in semantic_matches
    }
    selected_datasets = tuple(datasets_by_id.values())

    if not selected_datasets:
        return non_answer_catalog.non_answer(
            contracts.NonAnswerReasonCode.NO_MATCHING_DATASET,
            stage=contracts.NonAnswerStage.SEMANTIC_ROUTER,
        )
    if len(selected_datasets) > 1:
        return non_answer_catalog.non_answer(
            contracts.NonAnswerReasonCode.AMBIGUOUS_DATASET,
            stage=contracts.NonAnswerStage.SEMANTIC_ROUTER,
        )

    return contracts.Success(
        contracts.DatasetSelection(
            selected_datasets=selected_datasets,
            match_rationale=_build_match_rationale(semantic_matches[0]),
        ),
    )


def _build_match_rationale(match: contracts.SemanticMatch) -> str:
    if not match.group_by_fields:
        return f"{match.dataset.name} contains the {match.metric.label} metric."
    group_by_labels = ", ".join(field.label for field in match.group_by_fields)
    return (
        f"{match.dataset.name} contains the {match.metric.label} metric and "
        f"{group_by_labels} fields needed for the Data Question."
    )

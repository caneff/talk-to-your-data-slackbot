"""Semantic Router for Data Assistant Dataset Selection."""

from __future__ import annotations

import data_assistant.non_answer_catalog as non_answer_catalog
import data_assistant.semantic_layer.catalog as semantic_layer_catalog
import data_assistant.semantic_matcher as semantic_matcher
import data_assistant.workflow.contracts as contracts


def resolve_available_data(
    question_frame: contracts.QuestionFrame,
    semantic_layer: semantic_layer_catalog.SemanticLayerCatalog,
) -> contracts.StageResult[contracts.AvailableDataResolution]:
    """Resolve Available Data evidence to one dataset-backed semantic match."""
    semantic_matches = semantic_matcher.find_semantic_matches(
        question_frame=question_frame,
        semantic_layer=semantic_layer,
    )
    dataset_selection_result = select_dataset(semantic_matches)
    if isinstance(dataset_selection_result, contracts.NonAnswer):
        return dataset_selection_result
    resolved_match_result = resolve_semantic_match(
        semantic_matches,
        dataset_selection_result.value,
    )
    if isinstance(resolved_match_result, contracts.NonAnswer):
        return resolved_match_result

    return contracts.Success(
        contracts.AvailableDataResolution(
            resolved_match=resolved_match_result.value,
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
    first_match = semantic_matches[0]

    return contracts.Success(
        contracts.DatasetSelection(
            selected_datasets=selected_datasets,
            match_rationale=_build_match_rationale(first_match),
        ),
    )


def resolve_semantic_match(
    semantic_matches: tuple[contracts.SemanticMatch, ...],
    dataset_selection: contracts.DatasetSelection,
) -> contracts.StageResult[contracts.SemanticMatch]:
    """Resolve one canonical table match inside selected dataset."""
    dataset = dataset_selection.selected_datasets[0]
    table_options = tuple(
        match
        for match in semantic_matches
        if match.dataset.dataset_id == dataset.dataset_id
    )
    if not table_options:
        return non_answer_catalog.non_answer(
            contracts.NonAnswerReasonCode.NO_MATCHING_TABLE,
            stage=contracts.NonAnswerStage.SEMANTIC_ROUTER,
        )
    if len(table_options) > 1:
        return non_answer_catalog.non_answer(
            contracts.NonAnswerReasonCode.AMBIGUOUS_TABLE,
            stage=contracts.NonAnswerStage.SEMANTIC_ROUTER,
        )
    resolved_match = next(iter(table_options))
    return contracts.Success(resolved_match)


def _build_match_rationale(match: contracts.SemanticMatch) -> str:
    if not match.group_by_fields:
        return f"{match.dataset.name} contains the {match.metric.label} metric."
    group_by_labels = ", ".join(field.label for field in match.group_by_fields)
    return (
        f"{match.dataset.name} contains the {match.metric.label} metric and "
        f"{group_by_labels} fields needed for the Data Question."
    )

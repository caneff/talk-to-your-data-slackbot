"""Semantic Router for Data Assistant Dataset Selection."""

from __future__ import annotations

import data_assistant.workflow.contracts as contracts


def select_dataset(
    semantic_matches: tuple[contracts.SemanticMatch, ...],
) -> contracts.StageResult[contracts.DatasetSelection]:
    """Choose the Curated Dataset represented by Semantic Layer matches."""
    datasets_by_id = {
        match.dataset.dataset_id: match.dataset for match in semantic_matches
    }
    selected_datasets = tuple(datasets_by_id.values())

    if not selected_datasets:
        return contracts.NonAnswer(
            stage=contracts.NonAnswerStage.SEMANTIC_ROUTER,
            reason_code=contracts.NonAnswerReasonCode.NO_MATCHING_DATASET,
            reason="No Curated Dataset safely matches the Question Frame.",
            unresolved_ambiguities=("curated dataset",),
            next_step="Ask which approved business data should be used.",
        )
    if len(selected_datasets) > 1:
        return contracts.NonAnswer(
            stage=contracts.NonAnswerStage.SEMANTIC_ROUTER,
            reason_code=contracts.NonAnswerReasonCode.AMBIGUOUS_DATASET,
            reason="Multiple Curated Datasets match the Question Frame.",
            unresolved_ambiguities=("curated dataset",),
            next_step="Ask which Curated Dataset should be used.",
        )

    return contracts.Success(
        contracts.DatasetSelection(
            selected_datasets=selected_datasets,
            match_rationale=_build_match_rationale(semantic_matches[0]),
        ),
    )


def _build_match_rationale(match: contracts.SemanticMatch) -> str:
    return (
        f"{match.dataset.name} contains the {match.metric.label} metric and "
        f"{match.dimension.label} dimension needed for the Data Question."
    )

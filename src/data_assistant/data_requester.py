"""Data Requester step for Data Assistant Data Request creation."""

from __future__ import annotations

import data_assistant.workflow.contracts as contracts

DEFAULT_RESULT_LIMIT = 10


def create_data_request(
    question_frame: contracts.QuestionFrame,
    dataset_selection: contracts.DatasetSelection,
    semantic_matches: tuple[contracts.SemanticMatch, ...],
) -> contracts.StageResult[contracts.DataRequest]:
    """Create the Data Request from one selected Semantic Layer match."""
    if len(dataset_selection.selected_datasets) != 1:
        return contracts.NonAnswer(
            stage=contracts.NonAnswerStage.DATA_REQUESTER,
            reason_code=contracts.NonAnswerReasonCode.AMBIGUOUS_DATASET,
            reason="A Data Request requires exactly one Curated Dataset.",
            unresolved_ambiguities=("curated dataset",),
            next_step="Resolve dataset selection before planning retrieval.",
        )

    dataset = dataset_selection.selected_datasets[0]
    table_options = [
        match
        for match in semantic_matches
        if match.dataset.dataset_id == dataset.dataset_id
    ]

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

    match = table_options[0]
    return contracts.Success(
        contracts.DataRequest(
            dataset=match.dataset,
            table=match.table,
            metric=match.metric,
            dimension=match.dimension,
            time_range=question_frame.time_range,
            filters=question_frame.filters,
            output_shape=f"{match.metric.label} grouped by {match.dimension.label}",
            result_limit=DEFAULT_RESULT_LIMIT,
        ),
    )

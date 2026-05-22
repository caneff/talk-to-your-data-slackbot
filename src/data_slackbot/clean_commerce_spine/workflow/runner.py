"""Thin workflow runner for the clean commerce Data Assistant spine."""

from __future__ import annotations

import duckdb

from data_slackbot.clean_commerce_spine import (
    data_preparation,
    query_planner,
    question_interpreter,
    reasoning_layer,
    response_composer,
    semantic_router,
)
from data_slackbot.clean_commerce_spine import (
    semantic_layer as semantic_layer_module,
)
from data_slackbot.clean_commerce_spine.semantic_layer import schema
from data_slackbot.clean_commerce_spine.workflow import contracts


def run_clean_commerce_spine(
    connection: duckdb.DuckDBPyConnection,
    question: str,
    semantic_layer: schema.SemanticLayer | None = None,
) -> contracts.WorkflowResult:
    """Run the canonical clean Data Assistant path end to end."""
    active_semantic_layer = (
        semantic_layer or semantic_layer_module.load_semantic_layer()
    )
    question_frame_result = question_interpreter.interpret_question(
        question,
        active_semantic_layer,
    )
    if isinstance(question_frame_result, contracts.NonAnswer):
        return question_frame_result
    question_frame = question_frame_result.value

    dataset_selection_result = semantic_router.select_dataset(
        question_frame,
        active_semantic_layer,
    )
    if isinstance(dataset_selection_result, contracts.NonAnswer):
        return dataset_selection_result
    dataset_selection = dataset_selection_result.value

    data_request_result = query_planner.create_data_request(
        question_frame,
        dataset_selection,
        active_semantic_layer,
    )
    if isinstance(data_request_result, contracts.NonAnswer):
        return data_request_result
    data_request = data_request_result.value

    prepared_data = data_preparation.prepare_data(data_request, connection)
    answer_draft = reasoning_layer.draft_answer(prepared_data, active_semantic_layer)
    final_response = response_composer.compose_final_response(answer_draft)

    return contracts.DataAssistantRun(
        question_frame=question_frame,
        dataset_selection=dataset_selection,
        data_request=data_request,
        prepared_data=prepared_data,
        answer_draft=answer_draft,
        final_response=final_response,
    )

"""Thin workflow runner for the clean commerce Data Assistant spine."""

from __future__ import annotations

import duckdb

import data_slackbot.clean_commerce_spine.data_preparation as data_preparation
import data_slackbot.clean_commerce_spine.query_planner as query_planner
import data_slackbot.clean_commerce_spine.question_interpreter as question_interpreter
import data_slackbot.clean_commerce_spine.reasoning_layer as reasoning_layer
import data_slackbot.clean_commerce_spine.response_composer as response_composer
import data_slackbot.clean_commerce_spine.semantic_layer as semantic_layer_module
import data_slackbot.clean_commerce_spine.semantic_router as semantic_router
from data_slackbot.clean_commerce_spine.semantic_layer import schema
from data_slackbot.clean_commerce_spine.workflow.contracts import (
    DataAssistantRun,
    NonAnswer,
    WorkflowResult,
)


def run_clean_commerce_spine(
    connection: duckdb.DuckDBPyConnection,
    question: str,
    semantic_layer: schema.SemanticLayer | None = None,
) -> WorkflowResult:
    """Run the canonical clean Data Assistant path end to end."""
    active_semantic_layer = (
        semantic_layer or semantic_layer_module.load_semantic_layer()
    )
    question_frame_result = question_interpreter.interpret_question(
        question,
        active_semantic_layer,
    )
    if isinstance(question_frame_result, NonAnswer):
        return question_frame_result
    question_frame = question_frame_result.value

    dataset_selection_result = semantic_router.select_dataset(
        question_frame,
        active_semantic_layer,
    )
    if isinstance(dataset_selection_result, NonAnswer):
        return dataset_selection_result
    dataset_selection = dataset_selection_result.value

    data_request_result = query_planner.create_data_request(
        question_frame,
        dataset_selection,
        active_semantic_layer,
    )
    if isinstance(data_request_result, NonAnswer):
        return data_request_result
    data_request = data_request_result.value

    prepared_data = data_preparation.prepare_data(data_request, connection)
    answer_draft = reasoning_layer.draft_answer(prepared_data, active_semantic_layer)
    final_response = response_composer.compose_final_response(answer_draft)

    return DataAssistantRun(
        question_frame=question_frame,
        dataset_selection=dataset_selection,
        data_request=data_request,
        prepared_data=prepared_data,
        answer_draft=answer_draft,
        final_response=final_response,
    )

"""Thin workflow runner for the Data Assistant."""

from __future__ import annotations

import duckdb

import data_assistant.data_preparation as data_preparation
import data_assistant.query_planner as query_planner
import data_assistant.question_interpreter as question_interpreter
import data_assistant.reasoning_layer as reasoning_layer
import data_assistant.response_composer as response_composer
import data_assistant.semantic_layer.loader as semantic_layer_loader
import data_assistant.semantic_layer.schema as schema
import data_assistant.semantic_router as semantic_router
import data_assistant.workflow.contracts as contracts


def run_data_assistant(
    connection: duckdb.DuckDBPyConnection,
    question: str,
    semantic_layer: schema.SemanticLayer | None = None,
) -> contracts.WorkflowResult:
    """Run the canonical Data Assistant path end to end."""
    active_semantic_layer: schema.SemanticLayer
    if semantic_layer is None:
        active_semantic_layer = semantic_layer_loader.load_semantic_layer()
    else:
        active_semantic_layer = semantic_layer

    question_frame_result: contracts.StageResult[contracts.QuestionFrame]
    question_frame_result = question_interpreter.interpret_question(
        question=question,
        semantic_layer=active_semantic_layer,
    )
    if isinstance(question_frame_result, contracts.NonAnswer):
        return question_frame_result
    question_frame: contracts.QuestionFrame = question_frame_result.value

    dataset_selection_result: contracts.StageResult[contracts.DatasetSelection]
    dataset_selection_result = semantic_router.select_dataset(
        question_frame=question_frame,
        semantic_layer=active_semantic_layer,
    )
    if isinstance(dataset_selection_result, contracts.NonAnswer):
        return dataset_selection_result
    dataset_selection: contracts.DatasetSelection = dataset_selection_result.value

    data_request_result: contracts.StageResult[contracts.DataRequest]
    data_request_result = query_planner.create_data_request(
        question_frame=question_frame,
        dataset_selection=dataset_selection,
        semantic_layer=active_semantic_layer,
    )
    if isinstance(data_request_result, contracts.NonAnswer):
        return data_request_result
    data_request: contracts.DataRequest = data_request_result.value

    prepared_data: contracts.PreparedData = data_preparation.prepare_data(
        data_request=data_request,
        connection=connection,
    )
    answer_draft: contracts.AnswerDraft = reasoning_layer.draft_answer(
        prepared_data=prepared_data,
        semantic_layer=active_semantic_layer,
    )
    final_response: contracts.FinalResponse = (
        response_composer.compose_final_response(answer_draft=answer_draft)
    )

    return contracts.DataAssistantRun(
        question_frame=question_frame,
        dataset_selection=dataset_selection,
        data_request=data_request,
        prepared_data=prepared_data,
        answer_draft=answer_draft,
        final_response=final_response,
    )

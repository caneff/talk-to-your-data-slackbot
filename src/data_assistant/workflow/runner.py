"""Thin workflow runner for the Data Assistant."""

from __future__ import annotations

import duckdb

import data_assistant.access_controller as access_controller
import data_assistant.data_preparation as data_preparation
import data_assistant.data_requester as data_requester
import data_assistant.llm_question_interpreter as llm_question_interpreter
import data_assistant.reasoning_layer as reasoning_layer
import data_assistant.response_composer as response_composer
import data_assistant.semantic_layer.loader as semantic_layer_loader
import data_assistant.semantic_layer.schema as schema
import data_assistant.semantic_router as semantic_router
import data_assistant.workflow.contracts as contracts


def run_data_assistant(
    connection: duckdb.DuckDBPyConnection,
    question: str,
    *,
    question_interpreter_provider: llm_question_interpreter.QuestionInterpreterProvider,
    internal_identity: contracts.InternalIdentity | None = None,
    semantic_layer: schema.SemanticLayer | None = None,
) -> contracts.WorkflowResult:
    """Run the canonical Data Assistant path end to end."""
    active_semantic_layer: schema.SemanticLayer
    if semantic_layer is None:
        active_semantic_layer = semantic_layer_loader.load_semantic_layer()
    else:
        active_semantic_layer = semantic_layer
    active_internal_identity = internal_identity
    if active_internal_identity is None:
        active_internal_identity = access_controller.DEFAULT_LOCAL_ALLOWED_IDENTITY

    question_frame_result = llm_question_interpreter.interpret_question(
        question=question,
        semantic_layer=active_semantic_layer,
        provider=question_interpreter_provider,
    )
    if isinstance(question_frame_result, contracts.NonAnswer):
        return response_composer.compose_non_answer_response(question_frame_result)
    question_frame = question_frame_result.value

    dataset_selection_result = semantic_router.select_dataset(
        question_frame=question_frame,
        semantic_layer=active_semantic_layer,
    )
    if isinstance(dataset_selection_result, contracts.NonAnswer):
        return response_composer.compose_non_answer_response(dataset_selection_result)
    dataset_selection = dataset_selection_result.value

    dataset_access_result = access_controller.authorize_dataset_access(
        dataset_selection=dataset_selection,
        internal_identity=active_internal_identity,
    )
    if isinstance(dataset_access_result, contracts.NonAnswer):
        return response_composer.compose_non_answer_response(dataset_access_result)

    data_request_result = data_requester.create_data_request(
        question_frame=question_frame,
        dataset_selection=dataset_access_result.value,
        semantic_layer=active_semantic_layer,
    )
    if isinstance(data_request_result, contracts.NonAnswer):
        return response_composer.compose_non_answer_response(data_request_result)
    data_request = data_request_result.value

    prepared_data = data_preparation.prepare_data(
        data_request=data_request,
        connection=connection,
    )
    answer_draft = reasoning_layer.draft_answer(
        prepared_data=prepared_data,
    )
    final_response = response_composer.compose_final_response(
        answer_draft=answer_draft,
    )

    return contracts.DataAssistantRun(
        question_frame=question_frame,
        dataset_selection=dataset_selection,
        data_request=data_request,
        prepared_data=prepared_data,
        answer_draft=answer_draft,
        final_response=final_response,
    )

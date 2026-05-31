"""Thin workflow runner for the Data Assistant."""

from __future__ import annotations

import duckdb

import data_assistant.access_controller as access_controller
import data_assistant.data_preparation as data_preparation
import data_assistant.data_requester as data_requester
import data_assistant.non_answer_catalog as non_answer_catalog
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
    *,
    question_interpreter_provider: question_interpreter.QuestionInterpreterProvider,
    internal_identity: contracts.InternalIdentity,
    semantic_layer: schema.SemanticLayer | None = None,
) -> contracts.WorkflowResult:
    """Run the canonical Data Assistant path end to end.

    Parameters
    ----------
    connection
        DuckDB connection used to prepare bounded data.
    question
        User question to interpret, route, authorize, query, and answer.
    question_interpreter_provider
        Provider for the LLM-backed question interpreter.
    internal_identity
        Caller identity for access control.
    semantic_layer
        Semantic Layer to route against. Defaults to the configured layer.

    Returns
    -------
    contracts.WorkflowResult
        Composed non-answer, or ``DataAssistantRun`` with intermediate artifacts
        and final response.

    Notes
    -----
    Phases run in order: interpret the Data Question, resolve Available Data,
    authorize Available Data, prepare data, and synthesize the Final Response.
    A ``NonAnswer`` short-circuits immediately.
    """
    active_semantic_layer = (
        semantic_layer or semantic_layer_loader.load_semantic_layer()
    )

    # 1. Interpret Data Question.
    question_frame_result = question_interpreter.interpret_question(
        question=question,
        semantic_layer=active_semantic_layer,
        provider=question_interpreter_provider,
    )
    if isinstance(question_frame_result, contracts.NonAnswer):
        return response_composer.compose_non_answer_response(
            question_frame_result,
            wording_provider=non_answer_catalog.StaticCatalogWording(),
        )
    question_frame = question_frame_result.value

    # 2. Resolve Available Data.
    available_data_result = semantic_router.resolve_available_data(
        question_frame=question_frame,
        semantic_layer=active_semantic_layer,
    )
    if isinstance(available_data_result, contracts.NonAnswer):
        return response_composer.compose_non_answer_response(
            available_data_result,
            wording_provider=non_answer_catalog.StaticCatalogWording(),
        )
    available_data_resolution = available_data_result.value

    # 3. Authorize Available Data.
    dataset_access_result = access_controller.authorize_dataset_access(
        dataset_selection=available_data_resolution.dataset_selection,
        internal_identity=internal_identity,
    )
    if isinstance(dataset_access_result, contracts.NonAnswer):
        return response_composer.compose_non_answer_response(
            dataset_access_result,
            wording_provider=non_answer_catalog.StaticCatalogWording(),
        )

    # 4. Prepare Data.
    data_request_result = data_requester.create_data_request(
        question_frame=question_frame,
        resolved_match=available_data_resolution.resolved_match,
    )
    if isinstance(data_request_result, contracts.NonAnswer):
        return response_composer.compose_non_answer_response(
            data_request_result,
            wording_provider=non_answer_catalog.StaticCatalogWording(),
        )
    data_request = data_request_result.value

    prepared_data = data_preparation.prepare_data(
        data_request=data_request,
        connection=connection,
    )

    # 5. Synthesize Final Response.
    answer_draft = reasoning_layer.draft_answer(
        prepared_data=prepared_data,
    )
    final_response = response_composer.compose_final_response(
        answer_draft=answer_draft,
    )

    return contracts.DataAssistantRun(
        question_frame=question_frame,
        available_data_resolution=available_data_resolution,
        data_request=data_request,
        prepared_data=prepared_data,
        answer_draft=answer_draft,
        final_response=final_response,
    )

"""Shared pytest fixtures for Data Assistant workflow tests."""

import datetime
import typing

import pytest

import data_assistant.access_controller as access_controller
import data_assistant.data_requester as data_requester
import data_assistant.llm_question_interpreter as llm_question_interpreter
import data_assistant.local_orders_fixture as local_orders_fixture
import data_assistant.semantic_layer.loader as semantic_layer_loader
import data_assistant.semantic_layer.schema as schema
import data_assistant.semantic_router as semantic_router
import data_assistant.workflow.contracts as contracts

CANONICAL_DATA_QUESTION = "What was total revenue by region in January 2026?"
T = typing.TypeVar("T")


def unwrap_stage_result(result: contracts.StageResult[T]) -> T:
    """Return a successful stage value or fail the test with the NonAnswer."""
    if isinstance(result, contracts.NonAnswer):
        raise AssertionError(result)
    return result.value


class StaticQuestionInterpreterProvider:
    """Deterministic test double for the LLM question interpreter provider."""

    def __init__(
        self,
        proposal: llm_question_interpreter.QuestionFrameProposal,
    ) -> None:
        self._proposal = proposal

    def propose_question_frame(
        self,
        *,
        question: str,
        semantic_layer_context: dict[str, object],
    ) -> llm_question_interpreter.QuestionFrameProposal:
        """Return the configured proposal without calling an LLM."""
        del question, semantic_layer_context
        return self._proposal


def canonical_question_proposal() -> llm_question_interpreter.QuestionFrameProposal:
    """Return provider proposal for the canonical revenue-by-region question."""
    return llm_question_interpreter.QuestionFrameProposal(
        intent="summarize",
        metric="total revenue",
        dimension="region",
        time_range=llm_question_interpreter.TimeRangeProposal(
            label="January 2026",
            start_date=datetime.date(2026, 1, 1),
            end_date=datetime.date(2026, 1, 31),
        ),
        filters=(),
    )


def missing_time_range_proposal() -> llm_question_interpreter.QuestionFrameProposal:
    """Return provider proposal that omits the required time range."""
    return llm_question_interpreter.QuestionFrameProposal(
        intent="summarize",
        metric="total revenue",
        dimension="region",
        time_range=None,
        filters=(),
    )


@pytest.fixture
def active_semantic_layer() -> schema.SemanticLayer:
    """Load the configured Semantic Layer used by workflow tests."""
    return semantic_layer_loader.load_semantic_layer()


@pytest.fixture
def connect_orders() -> local_orders_fixture.OrdersConnector:
    """Expose the in-memory DuckDB orders connector as a fixture."""
    return local_orders_fixture.connect_orders


@pytest.fixture
def canonical_question() -> str:
    """Return the shared question covered by the demo dataset."""
    return CANONICAL_DATA_QUESTION


@pytest.fixture
def allowed_internal_identity() -> contracts.InternalIdentity:
    """Return an identity allowed to access the demo commerce dataset."""
    return access_controller.DEFAULT_LOCAL_ALLOWED_IDENTITY


@pytest.fixture
def canonical_question_provider(
) -> llm_question_interpreter.QuestionInterpreterProvider:
    """Return a fake provider that can answer the canonical question."""
    return StaticQuestionInterpreterProvider(canonical_question_proposal())


@pytest.fixture
def missing_time_range_provider(
) -> llm_question_interpreter.QuestionInterpreterProvider:
    """Return a fake provider that triggers missing-time-range NonAnswer."""
    return StaticQuestionInterpreterProvider(missing_time_range_proposal())


@pytest.fixture
def question_frame(
    canonical_question: str,
    active_semantic_layer: schema.SemanticLayer,
    canonical_question_provider: llm_question_interpreter.QuestionInterpreterProvider,
) -> contracts.QuestionFrame:
    """Build a valid Question Frame through the interpreter boundary."""
    return unwrap_stage_result(
        llm_question_interpreter.interpret_question(
            question=canonical_question,
            semantic_layer=active_semantic_layer,
            provider=canonical_question_provider,
        ),
    )


@pytest.fixture
def dataset_selection(
    question_frame: contracts.QuestionFrame,
    active_semantic_layer: schema.SemanticLayer,
) -> contracts.DatasetSelection:
    """Build the canonical Dataset Selection through the semantic router."""
    return unwrap_stage_result(
        semantic_router.select_dataset(question_frame, active_semantic_layer)
    )


@pytest.fixture
def data_request(
    question_frame: contracts.QuestionFrame,
    dataset_selection: contracts.DatasetSelection,
    active_semantic_layer: schema.SemanticLayer,
) -> contracts.DataRequest:
    """Build the canonical Data Request through the requester boundary."""
    return unwrap_stage_result(
        data_requester.create_data_request(
            question_frame,
            dataset_selection,
            active_semantic_layer,
        ),
    )

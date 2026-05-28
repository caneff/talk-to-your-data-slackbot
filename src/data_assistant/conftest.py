import typing

import pytest

import data_assistant.access_controller as access_controller
import data_assistant.data_requester as data_requester
import data_assistant.llm_question_interpreter as llm_question_interpreter
import data_assistant.semantic_layer.loader as semantic_layer_loader
import data_assistant.semantic_layer.schema as schema
import data_assistant.semantic_router as semantic_router
import data_assistant.testing_support as testing_support
import data_assistant.workflow.contracts as contracts

CANONICAL_DATA_QUESTION = "What was total revenue by region in January 2026?"
T = typing.TypeVar("T")


def unwrap_stage_result(result: contracts.StageResult[T]) -> T:
    if isinstance(result, contracts.NonAnswer):
        raise AssertionError(result)
    return result.value


class StaticQuestionInterpreterProvider:
    def __init__(self, provider_payload: object) -> None:
        self._provider_payload = provider_payload

    def propose_question_frame(
        self,
        *,
        question: str,
        prompt_context: dict[str, object],
    ) -> object:
        del question, prompt_context
        return self._provider_payload


def canonical_question_provider_payload() -> dict[str, object]:
    return {
        "intent": "summarize",
        "metric": "total revenue",
        "dimension": "region",
        "time_range": {
            "label": "January 2026",
            "start_date": "2026-01-01",
            "end_date": "2026-01-31",
        },
        "filters": (),
    }


def missing_time_range_provider_payload() -> dict[str, object]:
    return {
        "intent": "summarize",
        "metric": "total revenue",
        "dimension": "region",
        "time_range": None,
        "filters": (),
    }


@pytest.fixture
def active_semantic_layer() -> schema.SemanticLayer:
    return semantic_layer_loader.load_semantic_layer()


@pytest.fixture
def connect_orders() -> testing_support.OrdersConnector:
    return testing_support.connect_orders


@pytest.fixture
def canonical_question() -> str:
    return CANONICAL_DATA_QUESTION


@pytest.fixture
def allowed_internal_identity() -> contracts.InternalIdentity:
    return access_controller.DEFAULT_LOCAL_ALLOWED_IDENTITY


@pytest.fixture
def canonical_question_provider(
) -> llm_question_interpreter.QuestionInterpreterProvider:
    return StaticQuestionInterpreterProvider(canonical_question_provider_payload())


@pytest.fixture
def missing_time_range_provider(
) -> llm_question_interpreter.QuestionInterpreterProvider:
    return StaticQuestionInterpreterProvider(missing_time_range_provider_payload())


@pytest.fixture
def question_frame(
    canonical_question: str,
    active_semantic_layer: schema.SemanticLayer,
    canonical_question_provider: llm_question_interpreter.QuestionInterpreterProvider,
) -> contracts.QuestionFrame:
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
    return unwrap_stage_result(
        semantic_router.select_dataset(question_frame, active_semantic_layer)
    )


@pytest.fixture
def data_request(
    question_frame: contracts.QuestionFrame,
    dataset_selection: contracts.DatasetSelection,
    active_semantic_layer: schema.SemanticLayer,
) -> contracts.DataRequest:
    return unwrap_stage_result(
        data_requester.create_data_request(
            question_frame,
            dataset_selection,
            active_semantic_layer,
        ),
    )

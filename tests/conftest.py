import pytest

from talk_to_your_data_slackbot.clean_commerce_spine import (
    contracts,
    data_preparation,
    query_planner,
    question_interpreter,
    semantic_layer,
    semantic_router,
)


@pytest.fixture
def active_semantic_layer() -> contracts.SemanticLayer:
    return semantic_layer.default_semantic_layer()


@pytest.fixture
def question_frame() -> contracts.QuestionFrame:
    return question_interpreter.interpret_question(
        question_interpreter.CANONICAL_DATA_QUESTION,
    )


@pytest.fixture
def dataset_selection(
    question_frame: contracts.QuestionFrame,
    active_semantic_layer: contracts.SemanticLayer,
) -> contracts.DatasetSelection:
    return semantic_router.select_dataset(question_frame, active_semantic_layer)


@pytest.fixture
def data_request(
    question_frame: contracts.QuestionFrame,
    dataset_selection: contracts.DatasetSelection,
) -> contracts.DataRequest:
    return query_planner.create_data_request(question_frame, dataset_selection)


@pytest.fixture
def prepared_data(
    data_request: contracts.DataRequest,
    active_semantic_layer: contracts.SemanticLayer,
) -> contracts.PreparedData:
    return data_preparation.prepare_data(data_request, active_semantic_layer)

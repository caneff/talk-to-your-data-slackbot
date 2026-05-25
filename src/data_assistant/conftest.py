import collections.abc
import typing

import duckdb
import pytest

import data_assistant.data_preparation as data_preparation
import data_assistant.data_requester as data_requester
import data_assistant.question_interpreter as question_interpreter
import data_assistant.semantic_layer.loader as semantic_layer_loader
import data_assistant.semantic_layer.schema as schema
import data_assistant.semantic_router as semantic_router
import data_assistant.workflow.contracts as contracts

CANONICAL_DATA_QUESTION = "What was total revenue by region in January 2026?"
T = typing.TypeVar("T")


def unwrap_stage_result(result: contracts.StageResult[T]) -> T:
    if isinstance(result, contracts.NonAnswer):
        raise AssertionError(result)
    return result.value


@pytest.fixture
def active_semantic_layer() -> schema.SemanticLayer:
    return semantic_layer_loader.load_semantic_layer()


@pytest.fixture
def commerce_connection() -> collections.abc.Iterator[duckdb.DuckDBPyConnection]:
    connection = duckdb.connect(":memory:")
    connection.execute(
        """
        create table orders (
            order_date date,
            region varchar,
            revenue decimal(12, 2)
        )
        """,
    )
    connection.executemany(
        "insert into orders values (?, ?, ?)",
        (
            ("2026-01-03", "North", "1200.00"),
            ("2026-01-08", "South", "850.00"),
            ("2026-01-15", "West", "1600.00"),
            ("2026-01-22", "North", "300.00"),
            ("2026-01-28", "East", "950.00"),
        ),
    )
    yield connection
    connection.close()


@pytest.fixture
def canonical_question() -> str:
    return CANONICAL_DATA_QUESTION


@pytest.fixture
def question_frame(
    canonical_question: str,
    active_semantic_layer: schema.SemanticLayer,
) -> contracts.QuestionFrame:
    return unwrap_stage_result(
        question_interpreter.interpret_question(
            canonical_question,
            active_semantic_layer,
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


@pytest.fixture
def prepared_data(
    data_request: contracts.DataRequest,
    commerce_connection: duckdb.DuckDBPyConnection,
) -> contracts.PreparedData:
    return data_preparation.prepare_data(data_request, commerce_connection)

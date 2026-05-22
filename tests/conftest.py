import collections.abc

import duckdb
import pytest

from data_slackbot.clean_commerce_spine import (
    contracts,
    data_preparation,
    query_planner,
    question_interpreter,
    semantic_layer,
    semantic_router,
)


@pytest.fixture
def active_semantic_layer() -> contracts.SemanticLayer:
    return semantic_layer.load_semantic_layer()


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
    active_semantic_layer: contracts.SemanticLayer,
) -> contracts.DataRequest:
    return query_planner.create_data_request(
        question_frame,
        dataset_selection,
        active_semantic_layer,
    )


@pytest.fixture
def prepared_data(
    data_request: contracts.DataRequest,
    commerce_connection: duckdb.DuckDBPyConnection,
) -> contracts.PreparedData:
    return data_preparation.prepare_data(data_request, commerce_connection)

import datetime

import data_assistant.question_interpreter as question_interpreter
import data_assistant.semantic_layer.schema as schema
import data_assistant.semantic_layer.testing_support as semantic_layer_testing
import data_assistant.workflow.contracts as contracts


def test_canonical_data_question_creates_business_question_frame() -> None:
    semantic_layer = semantic_layer_testing.semantic_layer_with_table(
        metrics=(
            schema.Metric(
                metric_id="total_revenue",
                label="total revenue",
                expression="sum(revenue)",
                source_column="revenue",
            ),
        ),
        dimensions=(
            schema.Dimension(
                dimension_id="region",
                label="region",
                column="region",
            ),
        ),
    )

    result = question_interpreter.interpret_question(
        "What was total revenue by region in January 2026?",
        semantic_layer,
    )

    assert isinstance(result, contracts.Success)
    expected_question_frame = contracts.QuestionFrame(
        intent="summarize",
        metric="total revenue",
        dimension="region",
        time_range=contracts.TimeRange(
            label="January 2026",
            start_date=datetime.date(2026, 1, 1),
            end_date=datetime.date(2026, 1, 31),
        ),
        filters=(),
        unresolved_ambiguities=(),
    )
    assert result.value == expected_question_frame


def test_question_interpreter_returns_non_answer_for_missing_time_range() -> None:
    semantic_layer = semantic_layer_testing.semantic_layer_with_table()

    result = question_interpreter.interpret_question(
        "What was total revenue by region?",
        semantic_layer,
    )

    assert result == contracts.NonAnswer(
        stage="question_interpreter",
        reason="The Data Question is missing required interpretation details.",
        unresolved_ambiguities=("time range",),
        next_step="Ask a clarification question before selecting data.",
    )


def test_question_interpreter_returns_non_answer_for_unsupported_shape() -> None:
    semantic_layer = semantic_layer_testing.semantic_layer_with_table()

    result = question_interpreter.interpret_question(
        "Can you forecast revenue for next quarter?",
        semantic_layer,
    )

    assert result == contracts.NonAnswer(
        stage="question_interpreter",
        reason=(
            "The Data Assistant currently supports total revenue by region "
            "for one month."
        ),
        unresolved_ambiguities=("supported shape",),
        next_step=(
            "Ask: What was total revenue by region in January 2026?"
        ),
    )


def test_question_interpreter_returns_non_answer_for_user_provided_csv() -> None:
    semantic_layer = semantic_layer_testing.semantic_layer_with_table()

    result = question_interpreter.interpret_question(
        "Can you use my CSV file to show total revenue by region in January 2026?",
        semantic_layer,
    )

    assert result == contracts.NonAnswer(
        stage="question_interpreter",
        reason="User-provided CSV files are not supported data sources.",
        unresolved_ambiguities=("unsupported data",),
        next_step=(
            "Ask about an approved Curated Dataset in the Semantic Layer instead."
        ),
    )

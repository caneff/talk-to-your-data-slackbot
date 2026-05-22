import datetime

from data_slackbot.clean_commerce_spine import question_interpreter
from data_slackbot.clean_commerce_spine.semantic_layer import schema
from data_slackbot.clean_commerce_spine.workflow import contracts


def test_canonical_data_question_creates_business_question_frame(
    question_frame: contracts.QuestionFrame,
) -> None:
    assert question_frame.intent == "summarize"
    assert question_frame.metric == "total revenue"
    assert question_frame.dimension == "region"
    assert question_frame.time_range.label == "January 2026"
    assert question_frame.time_range.start_date == datetime.date(2026, 1, 1)
    assert question_frame.time_range.end_date == datetime.date(2026, 1, 31)
    assert question_frame.filters == ()
    assert question_frame.unresolved_ambiguities == ()


def test_question_interpreter_returns_non_answer_for_missing_time_range(
    active_semantic_layer: schema.SemanticLayer,
) -> None:
    result = question_interpreter.interpret_question(
        "What was total revenue by region?",
        active_semantic_layer,
    )

    assert result == contracts.NonAnswer(
        stage="question_interpreter",
        reason="The Data Question is missing required interpretation details.",
        unresolved_ambiguities=("time range",),
        next_step="Ask a clarification question before selecting data.",
    )

import datetime

import pytest

from data_slackbot.clean_commerce_spine import (
    contracts,
    question_interpreter,
)


def test_canonical_data_question_creates_business_question_frame(
    question_frame: contracts.QuestionFrame,
) -> None:
    assert question_frame.intent == "summarize"
    assert question_frame.metric == "total revenue"
    assert question_frame.dimension == "region"
    assert question_frame.time_range.label == "January 2026"
    assert question_frame.time_range.start == datetime.date(2026, 1, 1)
    assert question_frame.time_range.exclusive_end == datetime.date(2026, 2, 1)
    assert question_frame.filters == ()
    assert question_frame.unresolved_ambiguities == ()


def test_question_interpreter_rejects_non_canonical_question() -> None:
    with pytest.raises(ValueError, match="Only the canonical"):
        question_interpreter.interpret_question("What was revenue in February?")

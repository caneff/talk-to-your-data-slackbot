"""Unit tests for Question Interpreter deterministic guards.

These exercise the lightweight pre-provider guards directly, so each guard's
positive and negative phrasing is pinned without standing up a provider.
"""

import pytest

import data_assistant.question_interpreter.guards as guards

_AVAILABILITY_POSITIVES = [
    # The exact flagged case (interaction id 9db59acd).
    "what months do have revenue data?",
    "which months have data",
    "what months have data",
    "what data do you have",
    "what data do you have?",
    "what data is available",
    "what data exists",
    "do you have revenue data",
]

_AVAILABILITY_NEGATIVES = [
    "what was total revenue by region in january 2026?",
    # Contains the bare word "data" but is a real metric question.
    "what was revenue data by region in january 2026?",
    "what was customer count by customer region in january 2026?",
]


@pytest.mark.parametrize("question", _AVAILABILITY_POSITIVES)
def test_mentions_availability_intent_fires_on_coverage_phrasing(
    question: str,
) -> None:
    normalized = guards.normalize_question(question)

    assert guards.mentions_availability_intent(normalized) is True


@pytest.mark.parametrize("question", _AVAILABILITY_NEGATIVES)
def test_mentions_availability_intent_silent_on_metric_questions(
    question: str,
) -> None:
    normalized = guards.normalize_question(question)

    assert guards.mentions_availability_intent(normalized) is False

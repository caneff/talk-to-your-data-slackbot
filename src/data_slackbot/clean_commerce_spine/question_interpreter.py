"""Deterministic Question Interpreter for the canonical Data Question."""

from __future__ import annotations

import datetime

from data_slackbot.clean_commerce_spine import contracts

CANONICAL_DATA_QUESTION = "What was total revenue by region in January 2026?"


def interpret_question(question: str) -> contracts.QuestionFrame:
    """Create a Question Frame for the canonical clean commerce question."""
    if _normalize(question) != _normalize(CANONICAL_DATA_QUESTION):
        msg = "Only the canonical clean commerce Data Question is supported."
        raise ValueError(msg)

    return contracts.QuestionFrame(
        intent="summarize",
        metric="total revenue",
        dimension="region",
        time_range=contracts.TimeRange(
            label="January 2026",
            start=datetime.date(2026, 1, 1),
            exclusive_end=datetime.date(2026, 2, 1),
        ),
        filters=(),
        unresolved_ambiguities=(),
    )


def _normalize(question: str) -> str:
    return " ".join(question.casefold().strip().split())

"""Deterministic Question Interpreter for the canonical Data Question."""

from __future__ import annotations

import datetime
import re

import data_assistant.semantic_layer.schema as schema
import data_assistant.workflow.contracts as contracts

_MONTHS_BY_NAME = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}


def interpret_question(
    question: str,
    semantic_layer: schema.SemanticLayer,
) -> contracts.StageResult[contracts.QuestionFrame]:
    """Create a Question Frame by matching Semantic Layer business labels."""
    normalized_question = _normalize(question)
    metric = _find_one_metric_label(normalized_question, semantic_layer)
    dimension = _find_one_dimension_label(normalized_question, semantic_layer)
    time_range = _find_month_year_time_range(normalized_question)
    unresolved_ambiguities = tuple(
        ambiguity
        for ambiguity, value in (
            ("metric", metric),
            ("dimension", dimension),
            ("time range", time_range),
        )
        if value is None
    )

    if unresolved_ambiguities:
        return contracts.NonAnswer(
            stage="question_interpreter",
            reason="The Data Question is missing required interpretation details.",
            unresolved_ambiguities=unresolved_ambiguities,
            next_step="Ask a clarification question before selecting data.",
        )

    assert metric is not None
    assert dimension is not None
    assert time_range is not None
    return contracts.Success(
        contracts.QuestionFrame(
            intent="summarize",
            metric=metric,
            dimension=dimension,
            time_range=time_range,
            filters=(),
            unresolved_ambiguities=(),
        ),
    )


def _find_one_metric_label(
    normalized_question: str,
    semantic_layer: schema.SemanticLayer,
) -> str | None:
    labels = {
        metric.label
        for table in semantic_layer.tables
        for metric in table.metrics
        if _normalize(metric.label) in normalized_question
    }
    return _one(labels)


def _find_one_dimension_label(
    normalized_question: str,
    semantic_layer: schema.SemanticLayer,
) -> str | None:
    labels = {
        dimension.label
        for table in semantic_layer.tables
        for dimension in table.dimensions
        if _normalize(dimension.label) in normalized_question
    }
    return _one(labels)


def _find_month_year_time_range(normalized_question: str) -> contracts.TimeRange | None:
    match = re.search(
        r"\b("
        + "|".join(_MONTHS_BY_NAME)
        + r")\s+([0-9]{4})\b",
        normalized_question,
    )
    if match is None:
        return None

    month_name = match.group(1)
    year = int(match.group(2))
    month = _MONTHS_BY_NAME[month_name]
    start_date = datetime.date(year, month, 1)
    end_date = _month_end_date(year, month)
    label = f"{month_name.title()} {year}"
    return contracts.TimeRange(label=label, start_date=start_date, end_date=end_date)


def _month_end_date(year: int, month: int) -> datetime.date:
    if month == 12:
        return datetime.date(year, 12, 31)
    return datetime.date(year, month + 1, 1) - datetime.timedelta(days=1)


def _one(values: set[str]) -> str | None:
    if len(values) != 1:
        return None
    return next(iter(values))


def _normalize(question: str) -> str:
    return " ".join(question.casefold().strip().split())

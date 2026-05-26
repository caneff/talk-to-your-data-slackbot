"""Deterministic Question Interpreter for the canonical Data Question."""

from __future__ import annotations

import calendar
import collections.abc
import datetime
import re
import typing

import data_assistant.semantic_layer.schema as schema
import data_assistant.workflow.contracts as contracts

_SUPPORTED_SHAPE_REASON = (
    "The Data Assistant currently supports total revenue by region for one month."
)
_SUPPORTED_SHAPE_NEXT_STEP = (
    "Ask: What was total revenue by region in January 2026?"
)
_UNSUPPORTED_DATA_PATTERNS = (
    re.compile(r"\bcsv\b"),
    re.compile(r"\bupload\b"),
    re.compile(r"\bspreadsheet\b"),
    re.compile(r"\bsql\b"),
    re.compile(r"\btable\b"),
    re.compile(r"\bdatabase\b"),
)
_UNSUPPORTED_DATA_REASON = "User-provided CSV files are not supported data sources."
_UNSUPPORTED_DATA_NEXT_STEP = (
    "Ask about an approved Curated Dataset in the Semantic Layer instead."
)


def interpret_question(
    question: str,
    semantic_layer: schema.SemanticLayer,
) -> contracts.StageResult[contracts.QuestionFrame]:
    """Create a Question Frame by matching Semantic Layer business labels."""
    normalized_question = _normalize(question)
    if _mentions_unsupported_data(normalized_question):
        return contracts.NonAnswer(
            stage="question_interpreter",
            reason=_UNSUPPORTED_DATA_REASON,
            unresolved_ambiguities=("unsupported data",),
            next_step=_UNSUPPORTED_DATA_NEXT_STEP,
        )

    metric = _find_one_label(
        normalized_question,
        (table.metrics for table in semantic_layer.tables),
    )
    dimension = _find_one_label(
        normalized_question,
        (table.dimensions for table in semantic_layer.tables),
    )
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

    if unresolved_ambiguities and unresolved_ambiguities != ("time range",):
        return contracts.NonAnswer(
            stage="question_interpreter",
            reason=_SUPPORTED_SHAPE_REASON,
            unresolved_ambiguities=("supported shape",),
            next_step=_SUPPORTED_SHAPE_NEXT_STEP,
        )

    if unresolved_ambiguities:
        return contracts.NonAnswer(
            stage="question_interpreter",
            reason="The Data Question is missing required interpretation details.",
            unresolved_ambiguities=unresolved_ambiguities,
            next_step="Ask a clarification question before selecting data.",
        )

    # Assert for type checker here.
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


def _find_month_year_time_range(normalized_question: str) -> contracts.TimeRange | None:
    for match in re.finditer(r"\b[a-z]+\s+[0-9]{4}\b", normalized_question):
        try:
            start_date = datetime.datetime.strptime(
                match.group(0),
                "%B %Y",
            ).date()
        except ValueError:
            continue

        end_date = datetime.date(
            start_date.year,
            start_date.month,
            calendar.monthrange(start_date.year, start_date.month)[1],
        )
        label = start_date.strftime("%B %Y")
        return contracts.TimeRange(
            label=label,
            start_date=start_date,
            end_date=end_date,
        )

    return None


class _SemanticLabel(typing.Protocol):
    label: str


def _find_one_label(
    normalized_question: str,
    label_groups: collections.abc.Iterable[collections.abc.Iterable[_SemanticLabel]],
) -> str | None:
    matching_labels = {
        item.label
        for label_group in label_groups
        for item in label_group
        if _normalize(item.label) in normalized_question
    }
    if len(matching_labels) != 1:
        return None
    return next(iter(matching_labels))


def _normalize(question: str) -> str:
    return " ".join(question.casefold().strip().split())


def _mentions_unsupported_data(normalized_question: str) -> bool:
    return any(
        pattern.search(normalized_question)
        for pattern in _UNSUPPORTED_DATA_PATTERNS
    )

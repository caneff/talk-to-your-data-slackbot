"""Provider Proposal Validation tests for relative_window (ADR-0025).

The model classifies an as_of-anchored relative phrase into
`relative_window {field, unit, count}`; the interpreter computes the window from
`as_of_date` and types it into a RangeFilter on the named date field — the same
typed shape an explicit range_filter resolves to (ADR-0008). These tests pin
that the interpreter, not the model, owns the arithmetic, plus the rejection
paths: unknown/non-date field, missing as_of_date, and relative_window XOR a
date range_filter.
"""

from __future__ import annotations

import dataclasses
import datetime

import data_assistant.question_interpreter as question_interpreter
import data_assistant.semantic_layer.catalog as semantic_layer_catalog
import data_assistant.semantic_layer.testing_support as semantic_layer_testing
import data_assistant.workflow.contracts as contracts


def _layer_with_as_of(
    as_of_date: datetime.date | None = datetime.date(2026, 6, 30),
) -> semantic_layer_catalog.SemanticLayerCatalog:
    layer = semantic_layer_testing.semantic_layer_with_table()
    if as_of_date is None:
        return layer
    new_dataset = layer.datasets[0].model_copy(update={"as_of_date": as_of_date})
    return dataclasses.replace(layer, datasets=(new_dataset,))


class _StaticProvider:
    def __init__(self, proposal: question_interpreter.ProviderProposal) -> None:
        self._proposal = proposal

    def propose_question_frame(
        self,
        *,
        question: str,
        semantic_layer_context: dict[str, object],
    ) -> question_interpreter.ProviderProposal:
        del question, semantic_layer_context
        return self._proposal


def _relative_proposal(
    relative_window: question_interpreter.ProviderRelativeWindow,
    *field_operations: question_interpreter.ProviderFieldOperation,
) -> question_interpreter.ProviderProposal:
    return question_interpreter.ProviderProposal(
        intent="summarize",
        metric="total revenue",
        field_operations=field_operations,
        relative_window=relative_window,
    )


def test_relative_window_resolves_to_typed_range_filter_on_named_field() -> None:
    proposal = _relative_proposal(
        question_interpreter.ProviderRelativeWindow(
            field="order date",
            unit="quarter",
            count=1,
        ),
    )

    result = question_interpreter.interpret_question(
        question="What was total revenue last quarter?",
        semantic_layer=_layer_with_as_of(),
        provider=_StaticProvider(proposal),
    )

    assert isinstance(result, contracts.Success)
    assert result.value.time_scope == contracts.TimeScope.BOUNDED
    assert result.value.field_filters == (
        contracts.RangeFilter(
            field="order date",
            lower=datetime.date(2026, 1, 1),
            upper=datetime.date(2026, 3, 31),
        ),
    )


def test_relative_window_day_family_computes_yesterday() -> None:
    proposal = _relative_proposal(
        question_interpreter.ProviderRelativeWindow(
            field="order date",
            unit="day",
            count=1,
        ),
    )

    result = question_interpreter.interpret_question(
        question="What was total revenue yesterday?",
        semantic_layer=_layer_with_as_of(),
        provider=_StaticProvider(proposal),
    )

    assert isinstance(result, contracts.Success)
    assert result.value.field_filters == (
        contracts.RangeFilter(
            field="order date",
            lower=datetime.date(2026, 6, 29),
            upper=datetime.date(2026, 6, 29),
        ),
    )


def test_relative_window_unknown_field_non_answers() -> None:
    proposal = _relative_proposal(
        question_interpreter.ProviderRelativeWindow(
            field="not a field",
            unit="day",
            count=1,
        ),
    )

    result = question_interpreter.interpret_question(
        question="What was total revenue yesterday?",
        semantic_layer=_layer_with_as_of(),
        provider=_StaticProvider(proposal),
    )

    assert isinstance(result, contracts.NonAnswer)
    assert result.reason_code == contracts.NonAnswerReasonCode.UNKNOWN_SEMANTIC_LABEL


def test_relative_window_non_date_field_non_answers() -> None:
    proposal = _relative_proposal(
        question_interpreter.ProviderRelativeWindow(
            field="region",
            unit="day",
            count=1,
        ),
    )

    result = question_interpreter.interpret_question(
        question="What was total revenue yesterday?",
        semantic_layer=_layer_with_as_of(),
        provider=_StaticProvider(proposal),
    )

    assert isinstance(result, contracts.NonAnswer)
    assert (
        result.reason_code == contracts.NonAnswerReasonCode.UNSUPPORTED_FIELD_OPERATION
    )


def test_relative_window_without_as_of_date_non_answers() -> None:
    proposal = _relative_proposal(
        question_interpreter.ProviderRelativeWindow(
            field="order date",
            unit="day",
            count=1,
        ),
    )

    result = question_interpreter.interpret_question(
        question="What was total revenue yesterday?",
        semantic_layer=_layer_with_as_of(as_of_date=None),
        provider=_StaticProvider(proposal),
    )

    assert isinstance(result, contracts.NonAnswer)
    assert result.reason_code == contracts.NonAnswerReasonCode.INVALID_PROVIDER_OUTPUT


def test_relative_window_with_date_range_filter_is_mutually_exclusive() -> None:
    proposal = _relative_proposal(
        question_interpreter.ProviderRelativeWindow(
            field="order date",
            unit="day",
            count=1,
        ),
        question_interpreter.ProviderFieldOperation(
            operation="range_filter",
            field="order date",
            lower="2026-01-01",
            upper="2026-01-31",
        ),
    )

    result = question_interpreter.interpret_question(
        question="What was total revenue yesterday in January 2026?",
        semantic_layer=_layer_with_as_of(),
        provider=_StaticProvider(proposal),
    )

    assert isinstance(result, contracts.NonAnswer)
    assert result.reason_code == contracts.NonAnswerReasonCode.INVALID_PROVIDER_OUTPUT


def test_relative_window_with_non_date_filter_still_resolves() -> None:
    # A non-date filter (region include) does not collide with relative_window.
    proposal = _relative_proposal(
        question_interpreter.ProviderRelativeWindow(
            field="order date",
            unit="month",
            count=1,
        ),
        question_interpreter.ProviderFieldOperation(
            operation="include_filter",
            field="region",
            values=("West",),
        ),
    )

    result = question_interpreter.interpret_question(
        question="What was total revenue for the West region last month?",
        semantic_layer=_layer_with_as_of(),
        provider=_StaticProvider(proposal),
    )

    assert isinstance(result, contracts.Success)
    assert (
        contracts.RangeFilter(
            field="order date",
            lower=datetime.date(2026, 5, 1),
            upper=datetime.date(2026, 5, 31),
        )
        in result.value.field_filters
    )

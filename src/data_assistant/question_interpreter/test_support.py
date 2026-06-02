"""Shared fixtures and builders for Question Interpreter tests.

These helpers keep behavior-focused test files from repeating provider stubs,
canonical question setup, and default valid proposal construction.
"""

import typing

import data_assistant.question_interpreter as question_interpreter
import data_assistant.semantic_layer.testing_support as semantic_layer_testing
import data_assistant.workflow.contracts as contracts

CANONICAL_DATA_QUESTION = "What was total revenue by region in January 2026?"
_DEFAULT_FIELD_OPERATIONS = object()


def interpret_with_provider_proposal(
    provider_proposal: question_interpreter.QuestionFrameProposal,
) -> contracts.StageResult[contracts.QuestionFrame]:
    """Interpret the canonical question with a provider that returns one proposal."""
    return question_interpreter.interpret_question(
        question=CANONICAL_DATA_QUESTION,
        semantic_layer=semantic_layer_testing.semantic_layer_with_table(),
        provider=fixed_proposal_provider(provider_proposal),
    )


def fixed_proposal_provider(
    provider_proposal: question_interpreter.QuestionFrameProposal,
) -> question_interpreter.QuestionInterpreterProvider:
    """Build a fake provider that always returns one fixed proposal."""

    class FixedProposalProvider:
        def propose_question_frame(
            self,
            *,
            question: str,
            semantic_layer_context: dict[str, object],
        ) -> question_interpreter.QuestionFrameProposal:
            del question, semantic_layer_context
            return provider_proposal

    return FixedProposalProvider()


def provider_that_must_not_be_called() -> (
    question_interpreter.QuestionInterpreterProvider
):
    """Build a fake provider that fails if the interpreter calls it."""

    class MustNotBeCalledProvider:
        def propose_question_frame(
            self,
            *,
            question: str,
            semantic_layer_context: dict[str, object],
        ) -> question_interpreter.QuestionFrameProposal:
            del question, semantic_layer_context
            raise AssertionError("provider should not be called")

    return MustNotBeCalledProvider()


def provider_failure_provider(
    reason: str = "provider unavailable",
    diagnostic_class: (
        question_interpreter.ProviderFailureDiagnosticClass | None
    ) = None,
) -> question_interpreter.QuestionInterpreterProvider:
    """Build a fake provider that returns a ProviderFailure."""

    class ProviderFailureProvider:
        def propose_question_frame(
            self,
            *,
            question: str,
            semantic_layer_context: dict[str, object],
        ) -> question_interpreter.ProviderFailure:
            del question, semantic_layer_context
            return question_interpreter.ProviderFailure(
                reason=reason,
                diagnostic_class=diagnostic_class,
            )

    return ProviderFailureProvider()


def invalid_result_provider(
    provider_result: object,
) -> question_interpreter.QuestionInterpreterProvider:
    """Build a fake provider that violates the provider contract for tests."""

    class InvalidResultProvider:
        def propose_question_frame(
            self,
            *,
            question: str,
            semantic_layer_context: dict[str, object],
        ) -> question_interpreter.QuestionFrameProposal:
            del question, semantic_layer_context
            return typing.cast(
                question_interpreter.QuestionFrameProposal,
                provider_result,
            )

    return InvalidResultProvider()


def question_frame_proposal(
    *,
    intent: str | None = "summarize",
    metric: str | None = "total revenue",
    metric_ambiguity: str | None = None,
    all_time: bool = False,
    field_operations: (
        tuple[question_interpreter.FieldOperationProposal, ...] | object
    ) = _DEFAULT_FIELD_OPERATIONS,
) -> question_interpreter.QuestionFrameProposal:
    """Build a valid proposal while allowing each promoted field to be varied."""
    if field_operations is _DEFAULT_FIELD_OPERATIONS:
        active_field_operations = (
            question_interpreter.GroupByOperationProposal(
                operation="group_by",
                field="region",
            ),
            question_interpreter.RangeFilterOperationProposal(
                operation="range_filter",
                field="order date",
                lower="2026-01-01",
                upper="2026-01-31",
            ),
        )
    else:
        active_field_operations = typing.cast(
            tuple[question_interpreter.FieldOperationProposal, ...],
            field_operations,
        )

    return question_interpreter.QuestionFrameProposal(
        intent=intent,
        metric=metric,
        metric_ambiguity=metric_ambiguity,
        all_time=all_time,
        field_operations=active_field_operations,
    )

"""Shared fixtures and builders for Question Interpreter tests.

These helpers keep behavior-focused test files from repeating provider stubs,
canonical question setup, and default valid proposal construction.
"""

import datetime
import typing

import data_assistant.question_interpreter as question_interpreter
import data_assistant.semantic_layer.testing_support as semantic_layer_testing
import data_assistant.workflow.contracts as contracts

CANONICAL_DATA_QUESTION = "What was total revenue by region in January 2026?"
_DEFAULT_TIME_RANGE = object()


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


def provider_that_must_not_be_called(
) -> question_interpreter.QuestionInterpreterProvider:
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
    dimension: str | None = "region",
    time_range: question_interpreter.TimeRangeProposal | None | object = (
        _DEFAULT_TIME_RANGE
    ),
    filters: tuple[str, ...] = (),
) -> question_interpreter.QuestionFrameProposal:
    """Build a valid proposal while allowing each promoted field to be varied."""
    if time_range is _DEFAULT_TIME_RANGE:
        active_time_range: question_interpreter.TimeRangeProposal | None = (
            question_interpreter.TimeRangeProposal(
                label="January 2026",
                start_date=datetime.date(2026, 1, 1),
                end_date=datetime.date(2026, 1, 31),
            )
        )
    else:
        active_time_range = typing.cast(
            question_interpreter.TimeRangeProposal | None,
            time_range,
        )

    return question_interpreter.QuestionFrameProposal(
        intent=intent,
        metric=metric,
        dimension=dimension,
        time_range=active_time_range,
        filters=filters,
    )

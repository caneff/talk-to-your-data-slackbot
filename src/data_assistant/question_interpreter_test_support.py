import datetime
import typing

import data_assistant.llm_question_interpreter as llm_question_interpreter
import data_assistant.semantic_layer.testing_support as semantic_layer_testing
import data_assistant.workflow.contracts as contracts

CANONICAL_DATA_QUESTION = "What was total revenue by region in January 2026?"
_DEFAULT_TIME_RANGE = object()


def interpret_with_provider_proposal(
    provider_proposal: llm_question_interpreter.QuestionFrameProposal,
) -> contracts.StageResult[contracts.QuestionFrame]:
    return llm_question_interpreter.interpret_question(
        question=CANONICAL_DATA_QUESTION,
        semantic_layer=semantic_layer_testing.semantic_layer_with_table(),
        provider=proposal_provider(provider_proposal),
    )


def interpret_with_bad_provider_result(
    provider_result: object,
) -> contracts.StageResult[contracts.QuestionFrame]:
    return llm_question_interpreter.interpret_question(
        question=CANONICAL_DATA_QUESTION,
        semantic_layer=semantic_layer_testing.semantic_layer_with_table(),
        provider=bad_provider(provider_result),
    )


def proposal_provider(
    provider_proposal: llm_question_interpreter.QuestionFrameProposal | None,
) -> llm_question_interpreter.QuestionInterpreterProvider:
    class FakeProvider:
        def propose_question_frame(
            self,
            *,
            question: str,
            semantic_layer_context: dict[str, object],
        ) -> llm_question_interpreter.QuestionFrameProposal:
            del question, semantic_layer_context
            if provider_proposal is None:
                raise AssertionError("provider should not be called")
            return provider_proposal

    return FakeProvider()


def bad_provider(
    provider_result: object,
) -> llm_question_interpreter.QuestionInterpreterProvider:
    class BadProvider:
        def propose_question_frame(
            self,
            *,
            question: str,
            semantic_layer_context: dict[str, object],
        ) -> llm_question_interpreter.QuestionFrameProposal:
            del question, semantic_layer_context
            return typing.cast(
                llm_question_interpreter.QuestionFrameProposal,
                provider_result,
            )

    return BadProvider()


def question_frame_proposal(
    *,
    intent: str | None = "summarize",
    metric: str | None = "total revenue",
    dimension: str | None = "region",
    time_range: llm_question_interpreter.TimeRangeProposal | None | object = (
        _DEFAULT_TIME_RANGE
    ),
    filters: tuple[str, ...] = (),
) -> llm_question_interpreter.QuestionFrameProposal:
    if time_range is _DEFAULT_TIME_RANGE:
        active_time_range: llm_question_interpreter.TimeRangeProposal | None = (
            llm_question_interpreter.TimeRangeProposal(
                label="January 2026",
                start_date=datetime.date(2026, 1, 1),
                end_date=datetime.date(2026, 1, 31),
            )
        )
    else:
        active_time_range = typing.cast(
            llm_question_interpreter.TimeRangeProposal | None,
            time_range,
        )

    return llm_question_interpreter.QuestionFrameProposal(
        intent=intent,
        metric=metric,
        dimension=dimension,
        time_range=active_time_range,
        filters=filters,
    )

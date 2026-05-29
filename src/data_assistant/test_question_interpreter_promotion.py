import datetime

import data_assistant.llm_question_interpreter as llm_question_interpreter
import data_assistant.question_interpreter_test_support as interpreter_support
import data_assistant.semantic_layer.testing_support as semantic_layer_testing
import data_assistant.workflow.contracts as contracts


def test_provider_backed_interpreter_promotes_valid_question_frame_proposal() -> None:
    semantic_layer = semantic_layer_testing.semantic_layer_with_table()

    class FakeProvider:
        def propose_question_frame(
            self,
            *,
            question: str,
            semantic_layer_context: object,
        ) -> llm_question_interpreter.QuestionFrameProposal:
            assert question == interpreter_support.CANONICAL_DATA_QUESTION
            assert semantic_layer_context is not None
            return interpreter_support.question_frame_proposal()

    result = llm_question_interpreter.interpret_question(
        question=interpreter_support.CANONICAL_DATA_QUESTION,
        semantic_layer=semantic_layer,
        provider=FakeProvider(),
    )

    assert result == contracts.Success(
        contracts.QuestionFrame(
            intent="summarize",
            metric="total revenue",
            dimension="region",
            time_range=contracts.TimeRange(
                label="January 2026",
                start_date=datetime.date(2026, 1, 1),
                end_date=datetime.date(2026, 1, 31),
            ),
            filters=(),
            unresolved_ambiguities=(),
        )
    )


def test_provider_backed_interpreter_returns_typed_non_answer_for_missing_time_range(
) -> None:
    semantic_layer = semantic_layer_testing.semantic_layer_with_table()

    class FakeProvider:
        def propose_question_frame(
            self,
            *,
            question: str,
            semantic_layer_context: object,
        ) -> llm_question_interpreter.QuestionFrameProposal:
            del question, semantic_layer_context
            return interpreter_support.question_frame_proposal(time_range=None)

    result = llm_question_interpreter.interpret_question(
        question="What was total revenue by region?",
        semantic_layer=semantic_layer,
        provider=FakeProvider(),
    )

    assert result == contracts.NonAnswer(
        stage=contracts.NonAnswerStage.QUESTION_INTERPRETER,
        reason_code=contracts.NonAnswerReasonCode.MISSING_REQUIRED_FIELD,
        reason="The Data Question is missing required interpretation details.",
        unresolved_ambiguities=("time range",),
        next_step="Ask a clarification question before selecting data.",
    )


def test_provider_backed_interpreter_returns_typed_non_answer_for_unsupported_data(
) -> None:
    semantic_layer = semantic_layer_testing.semantic_layer_with_table()

    class FailIfCalledProvider:
        def propose_question_frame(
            self,
            *,
            question: str,
            semantic_layer_context: object,
        ) -> llm_question_interpreter.ProviderFailure:
            del question, semantic_layer_context
            raise AssertionError("provider should not be called")

    result = llm_question_interpreter.interpret_question(
        question=(
            "Can you use my CSV file to show total revenue by region in "
            "January 2026?"
        ),
        semantic_layer=semantic_layer,
        provider=FailIfCalledProvider(),
    )

    assert result == contracts.NonAnswer(
        stage=contracts.NonAnswerStage.QUESTION_INTERPRETER,
        reason_code=contracts.NonAnswerReasonCode.UNSUPPORTED_DATA,
        reason="User-provided CSV files are not supported data sources.",
        unresolved_ambiguities=("unsupported data",),
        next_step=(
            "Ask about an approved Curated Dataset in the Semantic Layer "
            "instead."
        ),
    )


def test_provider_backed_interpreter_returns_typed_non_answer_for_unsupported_intent(
) -> None:
    result = interpreter_support.interpret_with_provider_proposal(
        interpreter_support.question_frame_proposal(intent="forecast")
    )

    assert result == contracts.NonAnswer(
        stage=contracts.NonAnswerStage.QUESTION_INTERPRETER,
        reason_code=contracts.NonAnswerReasonCode.UNSUPPORTED_INTENT,
        reason=(
            "The Data Assistant does not support that Data Question intent "
            "yet."
        ),
        unresolved_ambiguities=("supported intent",),
        next_step="Ask: What was total revenue by region in January 2026?",
    )


def test_provider_backed_interpreter_returns_typed_non_answer_for_unknown_metric(
) -> None:
    result = interpreter_support.interpret_with_provider_proposal(
        interpreter_support.question_frame_proposal(metric="gross bookings")
    )

    assert result == contracts.NonAnswer(
        stage=contracts.NonAnswerStage.QUESTION_INTERPRETER,
        reason_code=contracts.NonAnswerReasonCode.UNKNOWN_SEMANTIC_LABEL,
        reason=(
            "The Data Assistant could not match the requested Semantic Layer "
            "labels."
        ),
        unresolved_ambiguities=("metric",),
        next_step="Use exact Semantic Layer metric and dimension labels.",
    )


def test_provider_backed_interpreter_returns_typed_non_answer_for_missing_dimension(
) -> None:
    result = interpreter_support.interpret_with_provider_proposal(
        interpreter_support.question_frame_proposal(dimension="")
    )

    assert result == contracts.NonAnswer(
        stage=contracts.NonAnswerStage.QUESTION_INTERPRETER,
        reason_code=contracts.NonAnswerReasonCode.MISSING_REQUIRED_FIELD,
        reason="The Data Question is missing required interpretation details.",
        unresolved_ambiguities=("dimension",),
        next_step="Ask a clarification question before selecting data.",
    )


def test_provider_backed_interpreter_returns_typed_non_answer_for_unsupported_filters(
) -> None:
    result = interpreter_support.interpret_with_provider_proposal(
        interpreter_support.question_frame_proposal(filters=("region = 'North'",))
    )

    assert result == contracts.NonAnswer(
        stage=contracts.NonAnswerStage.QUESTION_INTERPRETER,
        reason_code=contracts.NonAnswerReasonCode.UNSUPPORTED_FILTER,
        reason=(
            "The Data Assistant does not support provider-proposed filters "
            "yet."
        ),
        unresolved_ambiguities=("filters",),
        next_step="Ask the Data Question without filters for now.",
    )


def test_provider_backed_interpreter_returns_typed_non_answer_for_provider_failure(
) -> None:
    semantic_layer = semantic_layer_testing.semantic_layer_with_table()

    class FakeProvider:
        def propose_question_frame(
            self,
            *,
            question: str,
            semantic_layer_context: object,
        ) -> llm_question_interpreter.ProviderFailure:
            del question, semantic_layer_context
            return llm_question_interpreter.ProviderFailure(
                reason="provider unavailable",
            )

    result = llm_question_interpreter.interpret_question(
        question=interpreter_support.CANONICAL_DATA_QUESTION,
        semantic_layer=semantic_layer,
        provider=FakeProvider(),
    )

    assert result == contracts.NonAnswer(
        stage=contracts.NonAnswerStage.QUESTION_INTERPRETER,
        reason_code=contracts.NonAnswerReasonCode.PROVIDER_FAILURE,
        reason=(
            "The Question Interpreter provider could not produce a proposal."
        ),
        unresolved_ambiguities=("provider failure",),
        next_step="Retry after the provider is available again.",
    )


def test_provider_backed_interpreter_rejects_invalid_provider_output() -> None:
    result = llm_question_interpreter.interpret_question(
        question=interpreter_support.CANONICAL_DATA_QUESTION,
        semantic_layer=semantic_layer_testing.semantic_layer_with_table(),
        provider=interpreter_support.invalid_result_provider({"hello": "world"}),
    )

    assert result == contracts.NonAnswer(
        stage=contracts.NonAnswerStage.QUESTION_INTERPRETER,
        reason_code=contracts.NonAnswerReasonCode.INVALID_PROVIDER_OUTPUT,
        reason="The Question Interpreter provider returned invalid output.",
        unresolved_ambiguities=("provider output",),
        next_step="Fix the provider contract before retrying.",
    )


def test_provider_backed_interpreter_rejects_invalid_time_range_ordering() -> None:
    result = interpreter_support.interpret_with_provider_proposal(
        interpreter_support.question_frame_proposal(
            time_range=llm_question_interpreter.TimeRangeProposal(
                label="January 2026",
                start_date=datetime.date(2026, 1, 31),
                end_date=datetime.date(2026, 1, 1),
            )
        )
    )

    assert result == contracts.NonAnswer(
        stage=contracts.NonAnswerStage.QUESTION_INTERPRETER,
        reason_code=contracts.NonAnswerReasonCode.INVALID_PROVIDER_OUTPUT,
        reason="The Question Interpreter provider returned invalid output.",
        unresolved_ambiguities=("time range",),
        next_step="Fix the provider contract before retrying.",
    )

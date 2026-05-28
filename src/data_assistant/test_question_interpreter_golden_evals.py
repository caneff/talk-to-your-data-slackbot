import datetime
import typing

import data_assistant.llm_question_interpreter as llm_question_interpreter
import data_assistant.question_interpreter_test_support as interpreter_support
import data_assistant.semantic_layer.testing_support as semantic_layer_testing
import data_assistant.workflow.contracts as contracts


def test_golden_question_evals_cover_expected_contracts() -> None:
    eval_cases = (
        GoldenEvalCase(
            name="happy_path",
            provider_proposal=interpreter_support.question_frame_proposal(),
            expected=contracts.Success(
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
            ),
        ),
        GoldenEvalCase(
            name="missing_time_range",
            provider_proposal=interpreter_support.question_frame_proposal(
                time_range=None
            ),
            expected=contracts.NonAnswer(
                stage=contracts.NonAnswerStage.QUESTION_INTERPRETER,
                reason_code=contracts.NonAnswerReasonCode.MISSING_REQUIRED_FIELD,
                reason="The Data Question is missing required interpretation details.",
                unresolved_ambiguities=("time range",),
                next_step="Ask a clarification question before selecting data.",
            ),
        ),
        GoldenEvalCase(
            name="unsupported_data",
            question=(
                "Can you use my CSV file to show total revenue by region in "
                "January 2026?"
            ),
            provider_proposal=None,
            expected=contracts.NonAnswer(
                stage=contracts.NonAnswerStage.QUESTION_INTERPRETER,
                reason_code=contracts.NonAnswerReasonCode.UNSUPPORTED_DATA,
                reason="User-provided CSV files are not supported data sources.",
                unresolved_ambiguities=("unsupported data",),
                next_step=(
                    "Ask about an approved Curated Dataset in the Semantic "
                    "Layer instead."
                ),
            ),
        ),
        GoldenEvalCase(
            name="unsupported_intent",
            provider_proposal=interpreter_support.question_frame_proposal(
                intent="forecast"
            ),
            expected=contracts.NonAnswer(
                stage=contracts.NonAnswerStage.QUESTION_INTERPRETER,
                reason_code=contracts.NonAnswerReasonCode.UNSUPPORTED_INTENT,
                reason=(
                    "The Data Assistant does not support that Data Question "
                    "intent yet."
                ),
                unresolved_ambiguities=("supported intent",),
                next_step="Ask: What was total revenue by region in January 2026?",
            ),
        ),
        GoldenEvalCase(
            name="hallucinated_metric",
            provider_proposal=interpreter_support.question_frame_proposal(
                metric="gross bookings"
            ),
            expected=contracts.NonAnswer(
                stage=contracts.NonAnswerStage.QUESTION_INTERPRETER,
                reason_code=contracts.NonAnswerReasonCode.UNKNOWN_SEMANTIC_LABEL,
                reason=(
                    "The Data Assistant could not match the requested "
                    "Semantic Layer labels."
                ),
                unresolved_ambiguities=("metric",),
                next_step="Use exact Semantic Layer metric and dimension labels.",
            ),
        ),
        GoldenEvalCase(
            name="missing_dimension",
            provider_proposal=interpreter_support.question_frame_proposal(
                dimension=""
            ),
            expected=contracts.NonAnswer(
                stage=contracts.NonAnswerStage.QUESTION_INTERPRETER,
                reason_code=contracts.NonAnswerReasonCode.MISSING_REQUIRED_FIELD,
                reason="The Data Question is missing required interpretation details.",
                unresolved_ambiguities=("dimension",),
                next_step="Ask a clarification question before selecting data.",
            ),
        ),
        GoldenEvalCase(
            name="unsupported_filters",
            provider_proposal=interpreter_support.question_frame_proposal(
                filters=("region = 'North'",)
            ),
            expected=contracts.NonAnswer(
                stage=contracts.NonAnswerStage.QUESTION_INTERPRETER,
                reason_code=contracts.NonAnswerReasonCode.UNSUPPORTED_FILTER,
                reason=(
                    "The Data Assistant does not support provider-proposed "
                    "filters yet."
                ),
                unresolved_ambiguities=("filters",),
                next_step="Ask the Data Question without filters for now.",
            ),
        ),
        GoldenEvalCase(
            name="invalid_time_range_ordering",
            provider_proposal=interpreter_support.question_frame_proposal(
                time_range=llm_question_interpreter.TimeRangeProposal(
                    label="January 2026",
                    start_date=datetime.date(2026, 1, 31),
                    end_date=datetime.date(2026, 1, 1),
                )
            ),
            expected=contracts.NonAnswer(
                stage=contracts.NonAnswerStage.QUESTION_INTERPRETER,
                reason_code=contracts.NonAnswerReasonCode.INVALID_PROVIDER_OUTPUT,
                reason="The Question Interpreter provider returned invalid output.",
                unresolved_ambiguities=("time range",),
                next_step="Fix the provider contract before retrying.",
            ),
        ),
    )

    for case in eval_cases:
        provider = interpreter_support.proposal_provider(case.provider_proposal)
        result = llm_question_interpreter.interpret_question(
            question=case.question,
            semantic_layer=semantic_layer_testing.semantic_layer_with_table(),
            provider=provider,
        )
        assert result == case.expected, case.name


class GoldenEvalCase(typing.NamedTuple):
    name: str
    provider_proposal: llm_question_interpreter.QuestionFrameProposal | None
    expected: contracts.StageResult[contracts.QuestionFrame]
    question: str = interpreter_support.CANONICAL_DATA_QUESTION

import dataclasses
import datetime

import pytest

import data_assistant.question_interpreter as question_interpreter
import data_assistant.question_interpreter_test_support as interpreter_support
import data_assistant.semantic_layer.testing_support as semantic_layer_testing
import data_assistant.workflow.contracts as contracts


@dataclasses.dataclass(frozen=True)
class ContractSnapshotCase:
    name: str
    provider: question_interpreter.QuestionInterpreterProvider
    expected: contracts.StageResult[contracts.QuestionFrame]
    question: str = interpreter_support.CANONICAL_DATA_QUESTION


class ProviderFailureProvider:
    def propose_question_frame(
        self,
        *,
        question: str,
        semantic_layer_context: dict[str, object],
    ) -> question_interpreter.ProviderFailure:
        del question, semantic_layer_context
        return question_interpreter.ProviderFailure(reason="provider unavailable")


def snapshot_case(
    *,
    name: str,
    proposal: question_interpreter.QuestionFrameProposal,
    expected: contracts.StageResult[contracts.QuestionFrame],
    question: str = interpreter_support.CANONICAL_DATA_QUESTION,
) -> ContractSnapshotCase:
    return provider_snapshot_case(
        name=name,
        question=question,
        provider=interpreter_support.fixed_proposal_provider(proposal),
        expected=expected,
    )


def provider_snapshot_case(
    *,
    name: str,
    provider: question_interpreter.QuestionInterpreterProvider,
    expected: contracts.StageResult[contracts.QuestionFrame],
    question: str = interpreter_support.CANONICAL_DATA_QUESTION,
) -> ContractSnapshotCase:
    return ContractSnapshotCase(
        name=name,
        question=question,
        provider=provider,
        expected=expected,
    )


CONTRACT_SNAPSHOT_CASES = (
    snapshot_case(
        name="happy_path",
        proposal=interpreter_support.question_frame_proposal(),
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
    snapshot_case(
        name="missing_time_range",
        proposal=interpreter_support.question_frame_proposal(time_range=None),
        expected=contracts.NonAnswer(
            stage=contracts.NonAnswerStage.QUESTION_INTERPRETER,
            reason_code=contracts.NonAnswerReasonCode.MISSING_REQUIRED_FIELD,
            reason="The Data Question is missing required interpretation details.",
            unresolved_ambiguities=("time range",),
            next_step="Ask a clarification question before selecting data.",
        ),
    ),
    snapshot_case(
        name="missing_intent",
        proposal=interpreter_support.question_frame_proposal(intent=None),
        expected=contracts.NonAnswer(
            stage=contracts.NonAnswerStage.QUESTION_INTERPRETER,
            reason_code=contracts.NonAnswerReasonCode.MISSING_REQUIRED_FIELD,
            reason="The Data Question is missing required interpretation details.",
            unresolved_ambiguities=("intent",),
            next_step="Ask a clarification question before selecting data.",
        ),
    ),
    snapshot_case(
        name="missing_metric",
        proposal=interpreter_support.question_frame_proposal(metric=None),
        expected=contracts.NonAnswer(
            stage=contracts.NonAnswerStage.QUESTION_INTERPRETER,
            reason_code=contracts.NonAnswerReasonCode.MISSING_REQUIRED_FIELD,
            reason="The Data Question is missing required interpretation details.",
            unresolved_ambiguities=("metric",),
            next_step="Ask a clarification question before selecting data.",
        ),
    ),
    provider_snapshot_case(
        name="unsupported_data",
        question=(
            "Can you use my CSV file to show total revenue by region in January 2026?"
        ),
        provider=interpreter_support.provider_that_must_not_be_called(),
        expected=contracts.NonAnswer(
            stage=contracts.NonAnswerStage.QUESTION_INTERPRETER,
            reason_code=contracts.NonAnswerReasonCode.UNSUPPORTED_DATA,
            reason="User-provided CSV files are not supported data sources.",
            unresolved_ambiguities=("unsupported data",),
            next_step=(
                "Ask about an approved Curated Dataset in the Semantic Layer instead."
            ),
        ),
    ),
    snapshot_case(
        name="unsupported_intent",
        proposal=interpreter_support.question_frame_proposal(intent="forecast"),
        expected=contracts.NonAnswer(
            stage=contracts.NonAnswerStage.QUESTION_INTERPRETER,
            reason_code=contracts.NonAnswerReasonCode.UNSUPPORTED_INTENT,
            reason=(
                "The Data Assistant does not support that Data Question intent yet."
            ),
            unresolved_ambiguities=("supported intent",),
            next_step="Ask: What was total revenue by region in January 2026?",
        ),
    ),
    snapshot_case(
        name="hallucinated_metric",
        proposal=interpreter_support.question_frame_proposal(metric="gross bookings"),
        expected=contracts.NonAnswer(
            stage=contracts.NonAnswerStage.QUESTION_INTERPRETER,
            reason_code=contracts.NonAnswerReasonCode.UNKNOWN_SEMANTIC_LABEL,
            reason=(
                "The Data Assistant could not match the requested Semantic Layer "
                "labels."
            ),
            unresolved_ambiguities=("metric",),
            next_step="Use exact Semantic Layer metric and dimension labels.",
        ),
    ),
    snapshot_case(
        name="unknown_dimension",
        proposal=interpreter_support.question_frame_proposal(dimension="product"),
        expected=contracts.NonAnswer(
            stage=contracts.NonAnswerStage.QUESTION_INTERPRETER,
            reason_code=contracts.NonAnswerReasonCode.UNKNOWN_SEMANTIC_LABEL,
            reason=(
                "The Data Assistant could not match the requested Semantic Layer "
                "labels."
            ),
            unresolved_ambiguities=("dimension",),
            next_step="Use exact Semantic Layer metric and dimension labels.",
        ),
    ),
    snapshot_case(
        name="missing_dimension",
        proposal=interpreter_support.question_frame_proposal(dimension=""),
        expected=contracts.NonAnswer(
            stage=contracts.NonAnswerStage.QUESTION_INTERPRETER,
            reason_code=contracts.NonAnswerReasonCode.MISSING_REQUIRED_FIELD,
            reason="The Data Question is missing required interpretation details.",
            unresolved_ambiguities=("dimension",),
            next_step="Ask a clarification question before selecting data.",
        ),
    ),
    snapshot_case(
        name="unsupported_filters",
        proposal=interpreter_support.question_frame_proposal(
            filters=("region = 'North'",)
        ),
        expected=contracts.NonAnswer(
            stage=contracts.NonAnswerStage.QUESTION_INTERPRETER,
            reason_code=contracts.NonAnswerReasonCode.UNSUPPORTED_FILTER,
            reason=(
                "The Data Assistant does not support provider-proposed filters yet."
            ),
            unresolved_ambiguities=("filters",),
            next_step="Ask the Data Question without filters for now.",
        ),
    ),
    provider_snapshot_case(
        name="provider_failure",
        provider=ProviderFailureProvider(),
        expected=contracts.NonAnswer(
            stage=contracts.NonAnswerStage.QUESTION_INTERPRETER,
            reason_code=contracts.NonAnswerReasonCode.PROVIDER_FAILURE,
            reason="The Question Interpreter provider could not produce a proposal.",
            unresolved_ambiguities=("provider failure",),
            next_step="Retry after the provider is available again.",
        ),
    ),
    provider_snapshot_case(
        name="invalid_provider_output",
        provider=interpreter_support.invalid_result_provider({"hello": "world"}),
        expected=contracts.NonAnswer(
            stage=contracts.NonAnswerStage.QUESTION_INTERPRETER,
            reason_code=contracts.NonAnswerReasonCode.INVALID_PROVIDER_OUTPUT,
            reason="The Question Interpreter provider returned invalid output.",
            unresolved_ambiguities=("provider output",),
            next_step="Fix the provider contract before retrying.",
        ),
    ),
    snapshot_case(
        name="invalid_time_range_ordering",
        proposal=interpreter_support.question_frame_proposal(
            time_range=question_interpreter.TimeRangeProposal(
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


def contract_snapshot_id(case: ContractSnapshotCase) -> str:
    return case.name


@pytest.mark.parametrize(
    "case",
    CONTRACT_SNAPSHOT_CASES,
    ids=contract_snapshot_id,
)
def test_question_interpreter_returns_expected_contract(
    case: ContractSnapshotCase,
) -> None:
    result = question_interpreter.interpret_question(
        question=case.question,
        semantic_layer=semantic_layer_testing.semantic_layer_with_table(),
        provider=case.provider,
    )

    assert result == case.expected

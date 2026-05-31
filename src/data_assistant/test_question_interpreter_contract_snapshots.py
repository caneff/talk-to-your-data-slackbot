import dataclasses
import datetime

import pytest

import data_assistant.non_answer_catalog as non_answer_catalog
import data_assistant.question_interpreter as question_interpreter
import data_assistant.question_interpreter_test_support as interpreter_support
import data_assistant.semantic_layer.schema as schema
import data_assistant.semantic_layer.testing_support as semantic_layer_testing
import data_assistant.workflow.contracts as contracts

_STAGE = contracts.NonAnswerStage.QUESTION_INTERPRETER


@dataclasses.dataclass(frozen=True)
class ContractSnapshotCase:
    name: str
    provider: question_interpreter.QuestionInterpreterProvider
    expected: contracts.StageResult[contracts.QuestionFrame]
    question: str = interpreter_support.CANONICAL_DATA_QUESTION


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


# Non-Answer expectations are built through the catalog builders — the same
# dispatch production uses — so these cases assert routing (reason code, stage)
# and context (the field/label threaded in), not user-facing copy. Copy is
# pinned once in test_non_answer_catalog.py (ADR-0007).
CONTRACT_SNAPSHOT_CASES = (
    snapshot_case(
        name="happy_path",
        proposal=interpreter_support.question_frame_proposal(),
        expected=contracts.Success(
            contracts.QuestionFrame(
                intent="summarize",
                metric="total revenue",
                field_operations=(
                    contracts.SemanticFieldOperation(
                        operation=schema.FieldOperation.GROUP_BY,
                        field="region",
                    ),
                    contracts.SemanticFieldOperation(
                        operation=schema.FieldOperation.RANGE_FILTER,
                        field="order date",
                        lower=datetime.date(2026, 1, 1),
                        upper=datetime.date(2026, 1, 31),
                    ),
                ),
                unresolved_ambiguities=(),
            )
        ),
    ),
    snapshot_case(
        name="scalar_aggregate_without_group_by",
        proposal=interpreter_support.question_frame_proposal(
            field_operations=(
                question_interpreter.RangeFilterOperationProposal(
                    operation="range_filter",
                    field="order date",
                    lower="2026-01-01",
                    upper="2026-01-31",
                ),
            ),
        ),
        expected=contracts.Success(
            contracts.QuestionFrame(
                intent="summarize",
                metric="total revenue",
                field_operations=(
                    contracts.SemanticFieldOperation(
                        operation=schema.FieldOperation.RANGE_FILTER,
                        field="order date",
                        lower=datetime.date(2026, 1, 1),
                        upper=datetime.date(2026, 1, 31),
                    ),
                ),
                unresolved_ambiguities=(),
            )
        ),
    ),
    snapshot_case(
        name="exact_date_include_filter",
        proposal=interpreter_support.question_frame_proposal(
            field_operations=(
                question_interpreter.GroupByOperationProposal(
                    operation="group_by",
                    field="region",
                ),
                question_interpreter.IncludeFilterOperationProposal(
                    operation="include_filter",
                    field="order date",
                    values=("2026-01-15",),
                ),
            ),
        ),
        expected=contracts.Success(
            contracts.QuestionFrame(
                intent="summarize",
                metric="total revenue",
                field_operations=(
                    contracts.SemanticFieldOperation(
                        operation=schema.FieldOperation.GROUP_BY,
                        field="region",
                    ),
                    contracts.SemanticFieldOperation(
                        operation=schema.FieldOperation.INCLUDE_FILTER,
                        field="order date",
                        values=(datetime.date(2026, 1, 15),),
                    ),
                ),
                unresolved_ambiguities=(),
            )
        ),
    ),
    snapshot_case(
        name="missing_intent",
        proposal=interpreter_support.question_frame_proposal(intent=None),
        expected=non_answer_catalog.missing_required_field_non_answer(
            "intent", stage=_STAGE
        ),
    ),
    snapshot_case(
        name="missing_metric",
        proposal=interpreter_support.question_frame_proposal(metric=None),
        expected=non_answer_catalog.missing_required_field_non_answer(
            "metric", stage=_STAGE
        ),
    ),
    provider_snapshot_case(
        name="unsupported_data",
        question=(
            "Can you use my CSV file to show total revenue by region in January 2026?"
        ),
        provider=interpreter_support.provider_that_must_not_be_called(),
        expected=non_answer_catalog.non_answer(
            contracts.NonAnswerReasonCode.UNSUPPORTED_DATA, stage=_STAGE
        ),
    ),
    snapshot_case(
        name="unsupported_intent",
        proposal=interpreter_support.question_frame_proposal(intent="forecast"),
        expected=non_answer_catalog.non_answer(
            contracts.NonAnswerReasonCode.UNSUPPORTED_INTENT, stage=_STAGE
        ),
    ),
    snapshot_case(
        name="hallucinated_metric",
        proposal=interpreter_support.question_frame_proposal(metric="gross bookings"),
        expected=non_answer_catalog.unknown_semantic_label_non_answer(
            "metric", stage=_STAGE
        ),
    ),
    snapshot_case(
        name="unknown_field",
        proposal=interpreter_support.question_frame_proposal(
            field_operations=(
                question_interpreter.GroupByOperationProposal(
                    operation="group_by",
                    field="product",
                ),
            ),
        ),
        expected=non_answer_catalog.unknown_semantic_label_non_answer(
            "field", stage=_STAGE
        ),
    ),
    snapshot_case(
        name="unsupported_operation",
        proposal=interpreter_support.question_frame_proposal(
            field_operations=(
                question_interpreter.RangeFilterOperationProposal(
                    operation="range_filter",
                    field="region",
                    lower="A",
                    upper="Z",
                ),
            ),
        ),
        expected=non_answer_catalog.non_answer(
            contracts.NonAnswerReasonCode.UNSUPPORTED_FIELD_OPERATION, stage=_STAGE
        ),
    ),
    snapshot_case(
        name="invalid_value_coercion",
        proposal=interpreter_support.question_frame_proposal(
            field_operations=(
                question_interpreter.RangeFilterOperationProposal(
                    operation="range_filter",
                    field="order date",
                    lower="not-a-date",
                    upper="2026-01-31",
                ),
            ),
        ),
        expected=non_answer_catalog.non_answer(
            contracts.NonAnswerReasonCode.INVALID_PROVIDER_OUTPUT, stage=_STAGE
        ),
    ),
    snapshot_case(
        name="invalid_reversed_range",
        proposal=interpreter_support.question_frame_proposal(
            field_operations=(
                question_interpreter.RangeFilterOperationProposal(
                    operation="range_filter",
                    field="order date",
                    lower="2026-01-31",
                    upper="2026-01-01",
                ),
            ),
        ),
        expected=non_answer_catalog.non_answer(
            contracts.NonAnswerReasonCode.INVALID_PROVIDER_OUTPUT, stage=_STAGE
        ),
    ),
    snapshot_case(
        name="invalid_empty_filter_values",
        proposal=interpreter_support.question_frame_proposal(
            field_operations=(
                question_interpreter.IncludeFilterOperationProposal(
                    operation="include_filter",
                    field="region",
                    values=(),
                ),
            ),
        ),
        expected=non_answer_catalog.non_answer(
            contracts.NonAnswerReasonCode.INVALID_PROVIDER_OUTPUT, stage=_STAGE
        ),
    ),
    snapshot_case(
        name="multiple_group_by",
        proposal=interpreter_support.question_frame_proposal(
            field_operations=(
                question_interpreter.GroupByOperationProposal(
                    operation="group_by",
                    field="region",
                ),
                question_interpreter.GroupByOperationProposal(
                    operation="group_by",
                    field="region",
                ),
            ),
        ),
        expected=non_answer_catalog.non_answer(
            contracts.NonAnswerReasonCode.UNSUPPORTED_SHAPE, stage=_STAGE
        ),
    ),
    provider_snapshot_case(
        name="provider_failure",
        provider=interpreter_support.provider_failure_provider(),
        expected=non_answer_catalog.non_answer(
            contracts.NonAnswerReasonCode.PROVIDER_FAILURE, stage=_STAGE
        ),
    ),
    provider_snapshot_case(
        name="invalid_provider_output",
        provider=interpreter_support.invalid_result_provider({"hello": "world"}),
        expected=non_answer_catalog.non_answer(
            contracts.NonAnswerReasonCode.INVALID_PROVIDER_OUTPUT, stage=_STAGE
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


def test_question_interpreter_rejects_non_finite_decimal_filter_values() -> None:
    semantic_layer = semantic_layer_testing.semantic_layer_with_table(
        fields=(
            schema.SemanticField(
                field_id="revenue",
                label="revenue",
                source_column="revenue",
                data_type=schema.DataType.DECIMAL,
                operations=(schema.FieldOperation.RANGE_FILTER,),
            ),
        ),
    )
    proposal = question_interpreter.QuestionFrameProposal(
        intent="summarize",
        metric="total revenue",
        field_operations=(
            question_interpreter.RangeFilterOperationProposal(
                operation="range_filter",
                field="revenue",
                lower="NaN",
            ),
        ),
    )

    result = question_interpreter.interpret_question(
        question=interpreter_support.CANONICAL_DATA_QUESTION,
        semantic_layer=semantic_layer,
        provider=interpreter_support.fixed_proposal_provider(proposal),
    )

    assert result == non_answer_catalog.non_answer(
        contracts.NonAnswerReasonCode.INVALID_PROVIDER_OUTPUT, stage=_STAGE
    )


def test_question_interpreter_promotes_semantic_layer_operation_enum() -> None:
    result = interpreter_support.interpret_with_provider_proposal(
        interpreter_support.question_frame_proposal()
    )

    assert isinstance(result, contracts.Success)
    assert all(
        type(operation.operation) is schema.FieldOperation
        for operation in result.value.field_operations
    )

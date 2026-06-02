"""Promote untrusted Question Interpreter proposals to trusted Question Frames."""

from __future__ import annotations

import datetime
import decimal

import data_assistant.non_answer_catalog as non_answer_catalog
import data_assistant.semantic_layer.schema as schema
import data_assistant.workflow.contracts as contracts
from data_assistant.question_interpreter import guards as interpreter_guards
from data_assistant.question_interpreter import semantic_context
from data_assistant.question_interpreter.proposals import (
    FieldOperationProposal,
    ProviderFailure,
    QuestionFrameProposal,
    QuestionInterpreterProvider,
)

_SUPPORTED_PROVIDER_INTENTS = frozenset({"summarize"})


def interpret_question(
    *,
    question: str,
    semantic_layer: schema.SemanticLayer,
    provider: QuestionInterpreterProvider,
) -> contracts.StageResult[contracts.QuestionFrame]:
    """Promote validated provider proposal into a trusted Question Frame."""
    normalized_question = interpreter_guards.normalize_question(question)
    # Some requests are policy-level rejects; do not spend provider work on them.
    if interpreter_guards.mentions_unsupported_data(normalized_question):
        return non_answer_catalog.non_answer(
            contracts.NonAnswerReasonCode.UNSUPPORTED_DATA,
            stage=contracts.NonAnswerStage.QUESTION_INTERPRETER,
        )
    if interpreter_guards.mentions_rank_intent(normalized_question):
        return non_answer_catalog.non_answer(
            contracts.NonAnswerReasonCode.UNSUPPORTED_INTENT,
            stage=contracts.NonAnswerStage.QUESTION_INTERPRETER,
        )
    if interpreter_guards.mentions_availability_intent(normalized_question):
        return non_answer_catalog.non_answer(
            contracts.NonAnswerReasonCode.UNSUPPORTED_AVAILABILITY,
            stage=contracts.NonAnswerStage.QUESTION_INTERPRETER,
        )

    # Semantic Layer context is intentionally business-facing: labels and
    # examples, not table names, SQL, column names, or access internals.
    semantic_layer_context = semantic_context.build_semantic_layer_context(
        semantic_layer
    )
    try:
        raw_provider_result = provider.propose_question_frame(
            question=question,
            semantic_layer_context=semantic_layer_context,
        )
    except Exception:
        return non_answer_catalog.non_answer(
            contracts.NonAnswerReasonCode.PROVIDER_FAILURE,
            stage=contracts.NonAnswerStage.QUESTION_INTERPRETER,
        )

    # Provider output is only a proposal until workflow validation promotes it
    # into the trusted Question Frame contract.
    return _promote_provider_result(raw_provider_result, semantic_layer)


def _promote_provider_result(
    raw_provider_result: object,
    semantic_layer: schema.SemanticLayer,
) -> contracts.StageResult[contracts.QuestionFrame]:
    if isinstance(raw_provider_result, ProviderFailure):
        return non_answer_catalog.non_answer(
            contracts.NonAnswerReasonCode.PROVIDER_FAILURE,
            stage=contracts.NonAnswerStage.QUESTION_INTERPRETER,
        )
    if not isinstance(raw_provider_result, QuestionFrameProposal):
        return non_answer_catalog.non_answer(
            contracts.NonAnswerReasonCode.INVALID_PROVIDER_OUTPUT,
            stage=contracts.NonAnswerStage.QUESTION_INTERPRETER,
        )

    proposal = raw_provider_result
    intent_value = proposal.intent
    metric_value = proposal.metric

    # Apply current workflow limits before promoting to trusted contract.
    if not intent_value:
        return non_answer_catalog.missing_required_field_non_answer(
            "intent",
            stage=contracts.NonAnswerStage.QUESTION_INTERPRETER,
        )
    if intent_value not in _SUPPORTED_PROVIDER_INTENTS:
        return non_answer_catalog.non_answer(
            contracts.NonAnswerReasonCode.UNSUPPORTED_INTENT,
            stage=contracts.NonAnswerStage.QUESTION_INTERPRETER,
        )
    if not metric_value:
        return non_answer_catalog.missing_required_field_non_answer(
            "metric",
            stage=contracts.NonAnswerStage.QUESTION_INTERPRETER,
        )

    # Finally, prove provider labels are real Semantic Layer labels.
    if metric_value not in semantic_context.metric_labels(semantic_layer):
        return non_answer_catalog.unknown_semantic_label_non_answer(
            "metric",
            stage=contracts.NonAnswerStage.QUESTION_INTERPRETER,
        )
    field_operations_result = _promote_field_operations(
        proposal.field_operations,
        semantic_layer,
    )
    if isinstance(field_operations_result, contracts.NonAnswer):
        return field_operations_result
    time_scope = _derive_time_scope(
        proposal=proposal,
        field_operations=field_operations_result,
        semantic_layer=semantic_layer,
    )
    if isinstance(time_scope, contracts.NonAnswer):
        return time_scope

    return contracts.Success(
        contracts.QuestionFrame(
            intent=intent_value,
            metric=metric_value,
            field_operations=field_operations_result,
            unresolved_ambiguities=(),
            time_scope=time_scope,
        )
    )


def _derive_time_scope(
    *,
    proposal: QuestionFrameProposal,
    field_operations: tuple[contracts.SemanticFieldOperation, ...],
    semantic_layer: schema.SemanticLayer,
) -> contracts.TimeScope | contracts.NonAnswer:
    date_field_labels = {
        field.label
        for table in semantic_layer.tables
        for field in table.fields
        if field.data_type == schema.DataType.DATE
    }
    has_date_filter = any(
        operation.operation != schema.FieldOperation.GROUP_BY
        and operation.field in date_field_labels
        for operation in field_operations
    )
    if has_date_filter and proposal.all_time:
        return non_answer_catalog.non_answer(
            contracts.NonAnswerReasonCode.INVALID_PROVIDER_OUTPUT,
            stage=contracts.NonAnswerStage.QUESTION_INTERPRETER,
        )
    if has_date_filter:
        return contracts.TimeScope.BOUNDED
    if proposal.all_time:
        return contracts.TimeScope.ALL_TIME
    return non_answer_catalog.non_answer(
        contracts.NonAnswerReasonCode.MISSING_TIME_SCOPE,
        stage=contracts.NonAnswerStage.QUESTION_INTERPRETER,
    )


def _promote_field_operations(
    operation_proposals: tuple[FieldOperationProposal, ...],
    semantic_layer: schema.SemanticLayer,
) -> contracts.NonAnswer | tuple[contracts.SemanticFieldOperation, ...]:
    fields_by_label = {
        field.label: field for table in semantic_layer.tables for field in table.fields
    }
    promoted_operations: list[contracts.SemanticFieldOperation] = []
    group_by_count = 0
    for operation_proposal in operation_proposals:
        field = fields_by_label.get(operation_proposal.field)
        if field is None:
            return non_answer_catalog.unknown_semantic_label_non_answer(
                "field",
                stage=contracts.NonAnswerStage.QUESTION_INTERPRETER,
            )
        operation = schema.FieldOperation(operation_proposal.operation)
        if operation not in field.operations:
            return non_answer_catalog.non_answer(
                contracts.NonAnswerReasonCode.UNSUPPORTED_FIELD_OPERATION,
                stage=contracts.NonAnswerStage.QUESTION_INTERPRETER,
            )
        if operation == schema.FieldOperation.GROUP_BY:
            group_by_count += 1
            if group_by_count > 1:
                return non_answer_catalog.non_answer(
                    contracts.NonAnswerReasonCode.UNSUPPORTED_SHAPE,
                    stage=contracts.NonAnswerStage.QUESTION_INTERPRETER,
                )
            promoted_operations.append(
                contracts.SemanticFieldOperation(
                    operation=operation,
                    field=field.label,
                )
            )
            continue
        if operation == schema.FieldOperation.RANGE_FILTER:
            result = _promote_range_filter(operation_proposal, field, operation)
        elif operation in {
            schema.FieldOperation.INCLUDE_FILTER,
            schema.FieldOperation.EXCLUDE_FILTER,
        }:
            result = _promote_values_filter(operation_proposal, field, operation)
        else:
            return non_answer_catalog.non_answer(
                contracts.NonAnswerReasonCode.INVALID_PROVIDER_OUTPUT,
                stage=contracts.NonAnswerStage.QUESTION_INTERPRETER,
            )
        if isinstance(result, contracts.NonAnswer):
            return result
        promoted_operations.append(result)

    return tuple(promoted_operations)


def _promote_range_filter(
    operation_proposal: FieldOperationProposal,
    field: schema.SemanticField,
    operation: schema.FieldOperation,
) -> contracts.NonAnswer | contracts.SemanticFieldOperation:
    if operation_proposal.lower is None and operation_proposal.upper is None:
        return non_answer_catalog.non_answer(
            contracts.NonAnswerReasonCode.INVALID_PROVIDER_OUTPUT,
            stage=contracts.NonAnswerStage.QUESTION_INTERPRETER,
        )
    lower = (
        None
        if operation_proposal.lower is None
        else _coerce_field_value(operation_proposal.lower, field)
    )
    if isinstance(lower, contracts.NonAnswer):
        return lower
    upper = (
        None
        if operation_proposal.upper is None
        else _coerce_field_value(operation_proposal.upper, field)
    )
    if isinstance(upper, contracts.NonAnswer):
        return upper
    if _range_bounds_are_reversed(lower, upper):
        return non_answer_catalog.non_answer(
            contracts.NonAnswerReasonCode.INVALID_PROVIDER_OUTPUT,
            stage=contracts.NonAnswerStage.QUESTION_INTERPRETER,
        )
    return contracts.SemanticFieldOperation(
        operation=operation,
        field=field.label,
        lower=lower,
        upper=upper,
    )


def _range_bounds_are_reversed(
    lower: contracts.FieldValue | None,
    upper: contracts.FieldValue | None,
) -> bool:
    if lower is None or upper is None:
        return False
    if isinstance(lower, datetime.date) and isinstance(upper, datetime.date):
        return lower > upper
    if isinstance(lower, decimal.Decimal) and isinstance(upper, decimal.Decimal):
        return lower > upper
    if isinstance(lower, str) and isinstance(upper, str):
        return lower > upper
    return False


def _promote_values_filter(
    operation_proposal: FieldOperationProposal,
    field: schema.SemanticField,
    operation: schema.FieldOperation,
) -> contracts.NonAnswer | contracts.SemanticFieldOperation:
    if not operation_proposal.values:
        return non_answer_catalog.non_answer(
            contracts.NonAnswerReasonCode.INVALID_PROVIDER_OUTPUT,
            stage=contracts.NonAnswerStage.QUESTION_INTERPRETER,
        )
    coerced_values: list[contracts.FieldValue] = []
    for value in operation_proposal.values:
        coerced_value = _coerce_field_value(value, field)
        if isinstance(coerced_value, contracts.NonAnswer):
            return coerced_value
        coerced_values.append(coerced_value)
    return contracts.SemanticFieldOperation(
        operation=operation,
        field=field.label,
        values=tuple(coerced_values),
    )


def _coerce_field_value(
    value: str,
    field: schema.SemanticField,
) -> contracts.FieldValue | contracts.NonAnswer:
    if field.data_type == schema.DataType.DATE:
        try:
            return datetime.date.fromisoformat(value)
        except ValueError:
            return non_answer_catalog.non_answer(
                contracts.NonAnswerReasonCode.INVALID_PROVIDER_OUTPUT,
                stage=contracts.NonAnswerStage.QUESTION_INTERPRETER,
            )
    if field.data_type == schema.DataType.DECIMAL:
        try:
            coerced_value = decimal.Decimal(value)
        except decimal.InvalidOperation:
            return non_answer_catalog.non_answer(
                contracts.NonAnswerReasonCode.INVALID_PROVIDER_OUTPUT,
                stage=contracts.NonAnswerStage.QUESTION_INTERPRETER,
            )
        if not coerced_value.is_finite():
            return non_answer_catalog.non_answer(
                contracts.NonAnswerReasonCode.INVALID_PROVIDER_OUTPUT,
                stage=contracts.NonAnswerStage.QUESTION_INTERPRETER,
            )
        return coerced_value
    if field.data_type == schema.DataType.STRING:
        return value
    return non_answer_catalog.non_answer(
        contracts.NonAnswerReasonCode.INVALID_PROVIDER_OUTPUT,
        stage=contracts.NonAnswerStage.QUESTION_INTERPRETER,
    )

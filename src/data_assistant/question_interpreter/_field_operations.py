"""Internal Provider Proposal field-operation validation helpers."""

from __future__ import annotations

import datetime
import decimal

import data_assistant.non_answer_catalog as non_answer_catalog
import data_assistant.question_interpreter.proposals as proposals
import data_assistant.semantic_layer.catalog as semantic_layer_catalog
import data_assistant.semantic_layer.schema as schema
import data_assistant.workflow.contracts as contracts


def validate_field_filters(
    operation_proposals: tuple[proposals.ProviderFieldOperation, ...],
    semantic_layer: semantic_layer_catalog.SemanticLayerCatalog,
) -> contracts.NonAnswer | tuple[str | None, tuple[contracts.FieldFilter[str], ...]]:
    field_candidates_by_label = _field_candidates_by_label(semantic_layer)
    validated_filters: list[contracts.FieldFilter[str]] = []
    group_by_field: str | None = None
    for operation_proposal in operation_proposals:
        field_candidates = field_candidates_by_label.get(operation_proposal.field)
        if field_candidates is None:
            return non_answer_catalog.unknown_semantic_label_non_answer(
                "field",
                stage=contracts.NonAnswerStage.QUESTION_INTERPRETER,
            )
        if len(field_candidates) > 1:
            return non_answer_catalog.non_answer(
                contracts.NonAnswerReasonCode.INVALID_PROVIDER_OUTPUT,
                stage=contracts.NonAnswerStage.QUESTION_INTERPRETER,
            )
        field = field_candidates[0]
        operation = schema.FieldOperation(operation_proposal.operation)
        if operation not in field.operations:
            return non_answer_catalog.non_answer(
                contracts.NonAnswerReasonCode.UNSUPPORTED_FIELD_OPERATION,
                stage=contracts.NonAnswerStage.QUESTION_INTERPRETER,
            )
        if operation == schema.FieldOperation.GROUP_BY:
            if group_by_field is not None:
                return non_answer_catalog.non_answer(
                    contracts.NonAnswerReasonCode.UNSUPPORTED_SHAPE,
                    stage=contracts.NonAnswerStage.QUESTION_INTERPRETER,
                )
            group_by_field = field.label
            continue
        if operation == schema.FieldOperation.RANGE_FILTER:
            result = _validate_range_filter(operation_proposal, field, operation)
        elif operation in {
            schema.FieldOperation.INCLUDE_FILTER,
            schema.FieldOperation.EXCLUDE_FILTER,
        }:
            result = _validate_values_filter(operation_proposal, field, operation)
        else:
            return non_answer_catalog.non_answer(
                contracts.NonAnswerReasonCode.INVALID_PROVIDER_OUTPUT,
                stage=contracts.NonAnswerStage.QUESTION_INTERPRETER,
            )
        if isinstance(result, contracts.NonAnswer):
            return result
        validated_filters.append(result)

    return group_by_field, tuple(validated_filters)


def _field_candidates_by_label(
    semantic_layer: semantic_layer_catalog.SemanticLayerCatalog,
) -> dict[str, list[schema.SemanticField]]:
    field_candidates_by_label: dict[str, list[schema.SemanticField]] = {}
    for table in semantic_layer.tables:
        for field in table.fields:
            field_candidates_by_label.setdefault(field.label, []).append(field)
    return field_candidates_by_label


def _validate_range_filter(
    operation_proposal: proposals.ProviderFieldOperation,
    field: schema.SemanticField,
    operation: schema.FieldOperation,
) -> contracts.NonAnswer | contracts.RangeFilter[str]:
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
    del operation
    return contracts.RangeFilter(
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


def _validate_values_filter(
    operation_proposal: proposals.ProviderFieldOperation,
    field: schema.SemanticField,
    operation: schema.FieldOperation,
) -> contracts.NonAnswer | contracts.ValuesFilter[str]:
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
    mode = (
        contracts.FilterMode.INCLUDE
        if operation == schema.FieldOperation.INCLUDE_FILTER
        else contracts.FilterMode.EXCLUDE
    )
    return contracts.ValuesFilter(
        field=field.label,
        mode=mode,
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

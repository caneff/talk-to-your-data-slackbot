"""Data Requester step for Data Assistant Data Request creation."""

from __future__ import annotations

import data_assistant.semantic_layer.schema as schema
import data_assistant.workflow.contracts as contracts

DEFAULT_RESULT_LIMIT = 10


def create_data_request(
    question_frame: contracts.QuestionFrame,
    dataset_selection: contracts.DatasetSelection,
    semantic_matches: tuple[contracts.SemanticMatch, ...],
) -> contracts.StageResult[contracts.DataRequest]:
    """Create the Data Request from one selected Semantic Layer match."""
    if len(dataset_selection.selected_datasets) != 1:
        return contracts.NonAnswer(
            stage=contracts.NonAnswerStage.DATA_REQUESTER,
            reason_code=contracts.NonAnswerReasonCode.AMBIGUOUS_DATASET,
            reason="A Data Request requires exactly one Curated Dataset.",
            unresolved_ambiguities=("curated dataset",),
            next_step="Resolve dataset selection before planning retrieval.",
        )

    dataset = dataset_selection.selected_datasets[0]
    table_options = [
        match
        for match in semantic_matches
        if match.dataset.dataset_id == dataset.dataset_id
    ]

    if not table_options:
        return contracts.NonAnswer(
            stage=contracts.NonAnswerStage.DATA_REQUESTER,
            reason_code=contracts.NonAnswerReasonCode.NO_MATCHING_TABLE,
            reason="No Dataset Table can satisfy the Question Frame.",
            unresolved_ambiguities=("dataset table",),
            next_step="Ask which table-level metric or dimension should be used.",
        )
    if len(table_options) > 1:
        return contracts.NonAnswer(
            stage=contracts.NonAnswerStage.DATA_REQUESTER,
            reason_code=contracts.NonAnswerReasonCode.AMBIGUOUS_TABLE,
            reason="Multiple Dataset Tables can satisfy the Question Frame.",
            unresolved_ambiguities=("dataset table",),
            next_step="Ask which Dataset Table should be used.",
        )

    match = table_options[0]
    resolved_filters = _resolve_filter_operations(
        question_frame.field_operations,
        match.table,
    )
    if isinstance(resolved_filters, contracts.NonAnswer):
        return resolved_filters
    return contracts.Success(
        contracts.DataRequest(
            dataset=match.dataset,
            table=match.table,
            metric=match.metric,
            group_by_fields=match.group_by_fields,
            filter_operations=resolved_filters,
            output_shape=_output_shape(match),
            result_limit=DEFAULT_RESULT_LIMIT,
        ),
    )


def _resolve_filter_operations(
    field_operations: tuple[contracts.SemanticFieldOperation, ...],
    table: schema.DatasetTable,
) -> contracts.NonAnswer | tuple[contracts.ResolvedSemanticFieldOperation, ...]:
    fields_by_label = {field.label: field for field in table.fields}
    resolved: list[contracts.ResolvedSemanticFieldOperation] = []
    for operation in field_operations:
        if operation.operation == contracts.FieldOperationKind.GROUP_BY:
            continue
        field = fields_by_label.get(operation.field)
        if field is None:
            return contracts.NonAnswer(
                stage=contracts.NonAnswerStage.DATA_REQUESTER,
                reason_code=contracts.NonAnswerReasonCode.UNKNOWN_SEMANTIC_LABEL,
                reason=(
                    "The Data Assistant could not match the requested Semantic "
                    "Layer labels."
                ),
                unresolved_ambiguities=("field",),
                next_step="Use exact Semantic Layer field labels.",
            )
        resolved.append(
            contracts.ResolvedSemanticFieldOperation(
                operation=operation.operation,
                field=field,
                lower=operation.lower,
                upper=operation.upper,
                values=operation.values,
            )
        )
    return tuple(resolved)


def _output_shape(match: contracts.SemanticMatch) -> str:
    if not match.group_by_fields:
        return match.metric.label
    group_by_labels = ", ".join(field.label for field in match.group_by_fields)
    return f"{match.metric.label} grouped by {group_by_labels}"

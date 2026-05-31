"""Data Requester step for Data Assistant Data Request creation."""

from __future__ import annotations

import data_assistant.non_answer_catalog as non_answer_catalog
import data_assistant.semantic_layer.schema as schema
import data_assistant.workflow.contracts as contracts

DEFAULT_RESULT_LIMIT = 10


def create_data_request(
    question_frame: contracts.QuestionFrame,
    resolved_match: contracts.SemanticMatch,
) -> contracts.StageResult[contracts.DataRequest]:
    """Create the Data Request from one canonical Semantic Layer match."""
    resolved_filters = _resolve_filter_operations(
        question_frame.field_operations,
        resolved_match.table,
    )
    if isinstance(resolved_filters, contracts.NonAnswer):
        return resolved_filters
    return contracts.Success(
        contracts.DataRequest(
            dataset=resolved_match.dataset,
            table=resolved_match.table,
            metric=resolved_match.metric,
            group_by_fields=resolved_match.group_by_fields,
            filter_operations=resolved_filters,
            output_shape=_output_shape(resolved_match),
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
        if operation.operation == schema.FieldOperation.GROUP_BY:
            continue
        field = fields_by_label.get(operation.field)
        if field is None:
            return non_answer_catalog.unknown_semantic_label_non_answer(
                "field",
                stage=contracts.NonAnswerStage.SEMANTIC_ROUTER,
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

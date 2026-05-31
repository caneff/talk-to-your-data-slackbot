"""Semantic Layer matching for resolved data-access evidence."""

from __future__ import annotations

import data_assistant.semantic_layer.loader as semantic_layer_loader
import data_assistant.semantic_layer.schema as schema
import data_assistant.workflow.contracts as contracts


def find_semantic_matches(
    question_frame: contracts.QuestionFrame,
    semantic_layer: schema.SemanticLayer,
) -> tuple[contracts.SemanticMatch, ...]:
    """Find exact table-level Semantic Layer matches for a Question Frame."""
    matches: list[contracts.SemanticMatch] = []
    for dataset in semantic_layer.datasets:
        for table in semantic_layer_loader.tables_for_dataset(
            dataset,
            semantic_layer,
        ):
            metric = _find_metric(question_frame, table)
            group_by_fields = _find_group_by_fields(question_frame, table)
            if (
                metric is not None
                and group_by_fields is not None
                and _table_supports_filter_operations(question_frame, table)
            ):
                matches.append(
                    contracts.SemanticMatch(
                        dataset=dataset,
                        table=table,
                        metric=metric,
                        group_by_fields=group_by_fields,
                    ),
                )

    return tuple(matches)


def _find_metric(
    question_frame: contracts.QuestionFrame,
    table: schema.DatasetTable,
) -> schema.Metric | None:
    return next(
        (metric for metric in table.metrics if metric.label == question_frame.metric),
        None,
    )


def _find_group_by_fields(
    question_frame: contracts.QuestionFrame,
    table: schema.DatasetTable,
) -> tuple[schema.SemanticField, ...] | None:
    group_by_labels = tuple(
        operation.field
        for operation in question_frame.field_operations
        if operation.operation == contracts.FieldOperationKind.GROUP_BY
    )
    group_by_fields: list[schema.SemanticField] = []
    for group_by_label in group_by_labels:
        field = next(
            (
                table_field
                for table_field in table.fields
                if table_field.label == group_by_label
                and schema.FieldOperation.GROUP_BY in table_field.operations
            ),
            None,
        )
        if field is None:
            return None
        group_by_fields.append(field)
    return tuple(group_by_fields)


def _table_supports_filter_operations(
    question_frame: contracts.QuestionFrame,
    table: schema.DatasetTable,
) -> bool:
    fields_by_label = {field.label: field for field in table.fields}
    for operation in question_frame.field_operations:
        if operation.operation == contracts.FieldOperationKind.GROUP_BY:
            continue
        field = fields_by_label.get(operation.field)
        if field is None:
            return False
        if operation.operation not in field.operations:
            return False
    return True

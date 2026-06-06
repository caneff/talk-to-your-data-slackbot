"""Semantic Layer matching for resolved data-access evidence."""

from __future__ import annotations

import data_assistant.semantic_layer.catalog as semantic_layer_catalog
import data_assistant.semantic_layer.schema as schema
import data_assistant.workflow.contracts as contracts


def find_semantic_matches(
    question_frame: contracts.QuestionFrame,
    semantic_layer: semantic_layer_catalog.SemanticLayerCatalog,
) -> tuple[contracts.SemanticMatch, ...]:
    """Find exact table-level Semantic Layer matches for a Question Frame."""
    matches: list[contracts.SemanticMatch] = []
    for dataset in semantic_layer.datasets:
        for table in semantic_layer.tables_for_dataset_id(dataset.dataset_id):
            metric = _find_metric(question_frame, table)
            group_by_field = _find_group_by_field(question_frame, table)
            calendar_grouping = _find_calendar_grouping(question_frame, table)
            resolved_filters = _resolve_field_filters(question_frame, table)
            if (
                metric is not None
                and (
                    question_frame.group_by_field is None or group_by_field is not None
                )
                and (
                    question_frame.calendar_grouping is None
                    or calendar_grouping is not None
                )
                and resolved_filters is not None
            ):
                matches.append(
                    contracts.SemanticMatch(
                        dataset=dataset,
                        table=table,
                        metric=metric,
                        group_by_field=group_by_field,
                        calendar_grouping=calendar_grouping,
                        field_filters=resolved_filters,
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


def _find_group_by_field(
    question_frame: contracts.QuestionFrame,
    table: schema.DatasetTable,
) -> schema.SemanticField | None:
    if question_frame.group_by_field is None:
        return None
    return next(
        (
            table_field
            for table_field in table.fields
            if table_field.label == question_frame.group_by_field
            and schema.FieldOperation.GROUP_BY in table_field.operations
        ),
        None,
    )


def _find_calendar_grouping(
    question_frame: contracts.QuestionFrame,
    table: schema.DatasetTable,
) -> contracts.CalendarGrouping[schema.SemanticField] | None:
    if question_frame.calendar_grouping is None:
        return None
    field = next(
        (
            table_field
            for table_field in table.fields
            if table_field.label == question_frame.calendar_grouping.field
            and schema.FieldOperation.CALENDAR_GROUP_BY in table_field.operations
        ),
        None,
    )
    if field is None:
        return None
    return contracts.CalendarGrouping(
        field=field,
        grain=question_frame.calendar_grouping.grain,
    )


def _resolve_field_filters(
    question_frame: contracts.QuestionFrame,
    table: schema.DatasetTable,
) -> tuple[contracts.FieldFilter[schema.SemanticField], ...] | None:
    fields_by_label = {field.label: field for field in table.fields}
    resolved: list[contracts.FieldFilter[schema.SemanticField]] = []
    for field_filter in question_frame.field_filters:
        field = fields_by_label.get(field_filter.field)
        if field is None:
            return None
        if isinstance(field_filter, contracts.RangeFilter):
            if schema.FieldOperation.RANGE_FILTER not in field.operations:
                return None
            resolved.append(
                contracts.RangeFilter(
                    field=field,
                    lower=field_filter.lower,
                    upper=field_filter.upper,
                )
            )
            continue
        required_operation = (
            schema.FieldOperation.INCLUDE_FILTER
            if field_filter.mode == contracts.FilterMode.INCLUDE
            else schema.FieldOperation.EXCLUDE_FILTER
        )
        if required_operation not in field.operations:
            return None
        resolved.append(
            contracts.ValuesFilter(
                field=field,
                mode=field_filter.mode,
                values=field_filter.values,
            )
        )
    return tuple(resolved)

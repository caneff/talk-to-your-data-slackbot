"""Prepared Data step for supported Data Assistant metric questions."""

from __future__ import annotations

import duckdb

import data_assistant.semantic_layer.schema as schema
import data_assistant.workflow.contracts as contracts


def prepare_data(
    data_request: contracts.DataRequest,
    connection: duckdb.DuckDBPyConnection,
) -> contracts.PreparedData:
    """Produce bounded grouped Prepared Data from local DuckDB rows."""
    metric_source_column = data_request.metric.source_column
    group_by_field = data_request.group_by_field
    filter_sql, filter_parameters = _filter_sql(data_request.field_filters)
    filtered_rows_cte = f"""
        filtered_rows as (
            select *
            from {data_request.table.table_id}
            {filter_sql}
        )
    """
    if group_by_field is None:
        dimension_select = "'All'"
        group_and_order = "having count(*) > 0"
    else:
        dimension_select = _grouped_dimension_sql(group_by_field)
        group_and_order = (
            "group by dimension_value\n"
            "        order by metric_value desc, dimension_value asc"
        )
    metric_query = f"""
        with {filtered_rows_cte},
        metric_rows as (
            select *
            from filtered_rows
            where {metric_source_column} is not null
        )
        select
            {dimension_select} as dimension_value,
            {data_request.metric.expression} as metric_value
        from metric_rows
        {group_and_order}
        limit $result_limit
    """
    missing_dimension_expression = (
        "0" if group_by_field is None else _missing_dimension_sql(group_by_field)
    )
    quality_query = f"""
        with {filtered_rows_cte}
        select
            count(*) as filtered_row_count,
            coalesce(sum(
                case
                    when {metric_source_column} is null then 1
                    else 0
                end
            ), 0) as missing_metric_count,
            coalesce(sum({missing_dimension_expression}), 0)
                as missing_dimension_count
        from filtered_rows
    """

    prepared_dataframe = connection.execute(
        metric_query,
        {
            **filter_parameters,
            "result_limit": data_request.result_limit,
        },
    ).df()
    quality_counts = connection.execute(quality_query, filter_parameters).fetchone()
    assert quality_counts is not None
    filtered_row_count = int(quality_counts[0])
    missing_metric_count = int(quality_counts[1])
    missing_dimension_count = int(quality_counts[2])

    return contracts.PreparedData(
        request=data_request,
        data=prepared_dataframe,
        quality_notes=_quality_notes(
            filtered_row_count=filtered_row_count,
            metric_column=metric_source_column,
            dimension_label=group_by_field.label if group_by_field else "",
            missing_metric_count=missing_metric_count,
            missing_dimension_count=missing_dimension_count,
        ),
    )


def _filter_sql(
    field_filters: tuple[contracts.FieldFilter[schema.SemanticField], ...],
) -> tuple[str, dict[str, contracts.FieldValue]]:
    """Build a parameterized WHERE clause from validated filter operations.

    Column identifiers come from Semantic Layer source columns; every filter
    value is bound as a query parameter rather than interpolated into SQL.
    """
    clauses: list[str] = []
    parameters: dict[str, contracts.FieldValue] = {}

    def bind(index: int, suffix: str | int, value: contracts.FieldValue) -> str:
        """Register a value as a query parameter and return its placeholder."""
        name = f"filter_{index}_{suffix}"
        parameters[name] = value
        return f"${name}"

    for index, field_filter in enumerate(field_filters):
        column = field_filter.field.source_column
        if isinstance(field_filter, contracts.RangeFilter):
            if field_filter.lower is not None:
                clauses.append(
                    f"{column} >= {bind(index, 'lower', field_filter.lower)}"
                )
            if field_filter.upper is not None:
                clauses.append(
                    f"{column} <= {bind(index, 'upper', field_filter.upper)}"
                )
        else:
            placeholders = ", ".join(
                bind(index, value_index, value)
                for value_index, value in enumerate(field_filter.values)
            )
            sql_operator = (
                "in" if field_filter.mode == contracts.FilterMode.INCLUDE else "not in"
            )
            clauses.append(f"{column} {sql_operator} ({placeholders})")

    if not clauses:
        return "", {}
    return f"where {' and '.join(clauses)}", parameters


def _quality_notes(
    *,
    filtered_row_count: int,
    metric_column: str,
    dimension_label: str,
    missing_metric_count: int,
    missing_dimension_count: int,
) -> tuple[str, ...]:
    notes: list[str] = []
    if filtered_row_count == 0:
        notes.append("No rows matched the request filters.")
    if missing_metric_count:
        notes.append(
            f"{missing_metric_count} {_row_word(missing_metric_count)} excluded "
            f"because {metric_column} was missing.",
        )
    if missing_dimension_count:
        notes.append(
            f"{missing_dimension_count} {_row_word(missing_dimension_count)} grouped "
            f"under Unknown because {dimension_label} was missing.",
        )
    return tuple(notes)


def _row_word(count: int) -> str:
    if count == 1:
        return "row"
    return "rows"


def _grouped_dimension_sql(group_by_field: schema.SemanticField) -> str:
    column = group_by_field.source_column
    if group_by_field.data_type == schema.DataType.STRING:
        return f"coalesce(nullif(trim({column}), ''), 'Unknown')"
    return column


def _missing_dimension_sql(group_by_field: schema.SemanticField) -> str:
    column = group_by_field.source_column
    if group_by_field.data_type == schema.DataType.STRING:
        return f"""
                case
                    when {column} is null
                      or trim({column}) = '' then 1
                    else 0
                end
        """
    return f"""
                case
                    when {column} is null then 1
                    else 0
                end
    """

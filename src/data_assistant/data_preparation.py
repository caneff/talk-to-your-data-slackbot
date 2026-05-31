"""Prepared Data step for Data Assistant revenue by region."""

from __future__ import annotations

import duckdb

import data_assistant.workflow.contracts as contracts


def prepare_data(
    data_request: contracts.DataRequest,
    connection: duckdb.DuckDBPyConnection,
) -> contracts.PreparedData:
    """Produce bounded grouped Prepared Data from local DuckDB rows."""
    metric_source_column = data_request.metric.source_column
    group_by_field = (
        data_request.group_by_fields[0] if data_request.group_by_fields else None
    )
    dimension_value_expression = (
        None
        if group_by_field is None
        else f"coalesce(nullif(trim({group_by_field.source_column}), ''), 'Unknown')"
    )
    filter_sql, filter_parameters = _filter_sql(data_request.filter_operations)
    filtered_rows_cte = f"""
        filtered_rows as (
            select *
            from {data_request.table.table_id}
            {filter_sql}
        )
    """
    if dimension_value_expression is None:
        grouped_query = f"""
            with {filtered_rows_cte},
            metric_rows as (
                select *
                from filtered_rows
                where {metric_source_column} is not null
            )
            select
                'All' as dimension_value,
                {data_request.metric.expression} as metric_value
            from metric_rows
            limit $result_limit
        """
    else:
        grouped_query = f"""
        with {filtered_rows_cte},
        metric_rows as (
            select *
            from filtered_rows
            where {metric_source_column} is not null
        )
        select
            {dimension_value_expression} as dimension_value,
            {data_request.metric.expression} as metric_value
        from metric_rows
        group by dimension_value
        order by metric_value desc, dimension_value asc
        limit $result_limit
    """
    missing_dimension_expression = (
        "0"
        if group_by_field is None
        else f"""
                case
                    when {group_by_field.source_column} is null
                      or trim({group_by_field.source_column}) = '' then 1
                    else 0
                end
        """
    )
    quality_query = f"""
        with {filtered_rows_cte}
        select
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
        grouped_query,
        {
            **filter_parameters,
            "result_limit": data_request.result_limit,
        },
    ).df()
    quality_counts = connection.execute(quality_query, filter_parameters).fetchone()
    assert quality_counts is not None
    missing_metric_count = int(quality_counts[0])
    missing_dimension_count = int(quality_counts[1])

    return contracts.PreparedData(
        request=data_request,
        data=prepared_dataframe,
        quality_notes=_quality_notes(
            metric_column=metric_source_column,
            dimension_label=group_by_field.label if group_by_field else "",
            missing_metric_count=missing_metric_count,
            missing_dimension_count=missing_dimension_count,
        ),
    )


def _filter_sql(
    filter_operations: tuple[contracts.ResolvedSemanticFieldOperation, ...],
) -> tuple[str, dict[str, contracts.FieldValue]]:
    if not filter_operations:
        return "", {}
    clauses: list[str] = []
    parameters: dict[str, contracts.FieldValue] = {}
    for index, operation in enumerate(filter_operations):
        column = operation.field.source_column
        if operation.operation == contracts.FieldOperationKind.RANGE_FILTER:
            if operation.lower is not None:
                name = f"filter_{index}_lower"
                clauses.append(f"{column} >= ${name}")
                parameters[name] = operation.lower
            if operation.upper is not None:
                name = f"filter_{index}_upper"
                clauses.append(f"{column} <= ${name}")
                parameters[name] = operation.upper
        elif operation.operation == contracts.FieldOperationKind.INCLUDE_FILTER:
            names: list[str] = []
            for value_index, value in enumerate(operation.values):
                name = f"filter_{index}_{value_index}"
                names.append(f"${name}")
                parameters[name] = value
            clauses.append(f"{column} in ({', '.join(names)})")
        elif operation.operation == contracts.FieldOperationKind.EXCLUDE_FILTER:
            names: list[str] = []
            for value_index, value in enumerate(operation.values):
                name = f"filter_{index}_{value_index}"
                names.append(f"${name}")
                parameters[name] = value
            clauses.append(f"{column} not in ({', '.join(names)})")
    return f"where {' and '.join(clauses)}", parameters


def _quality_notes(
    *,
    metric_column: str,
    dimension_label: str,
    missing_metric_count: int,
    missing_dimension_count: int,
) -> tuple[str, ...]:
    notes: list[str] = []
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

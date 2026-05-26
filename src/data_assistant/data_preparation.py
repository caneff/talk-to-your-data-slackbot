"""Prepared Data step for Data Assistant revenue by region."""

from __future__ import annotations

import duckdb

import data_assistant.workflow.contracts as contracts


def prepare_data(
    data_request: contracts.DataRequest,
    connection: duckdb.DuckDBPyConnection,
) -> contracts.PreparedData:
    """Produce bounded grouped Prepared Data from local DuckDB rows."""
    metric_column = _sum_metric_column(data_request.metric.expression)
    dimension_value_expression = (
        f"coalesce(nullif(trim({data_request.dimension.column}), ''), 'Unknown')"
    )
    filtered_rows_cte = f"""
        filtered_rows as (
            select *
            from {data_request.table.table_id}
            where {data_request.table.date_column} >= $start_date
              and {data_request.table.date_column} <= $end_date
        )
    """
    grouped_query = f"""
        with {filtered_rows_cte},
        metric_rows as (
            select *
            from filtered_rows
            where {metric_column} is not null
        )
        select
            {dimension_value_expression} as dimension_value,
            sum({metric_column}) as metric_value
        from metric_rows
        group by dimension_value
        order by metric_value desc, dimension_value asc
        limit $result_limit
    """
    quality_query = f"""
        with {filtered_rows_cte}
        select
            sum(
                case
                    when {metric_column} is null then 1
                    else 0
                end
            ) as missing_metric_count,
            sum(
                case
                    when {data_request.dimension.column} is null
                      or trim({data_request.dimension.column}) = '' then 1
                    else 0
                end
            ) as missing_dimension_count
        from filtered_rows
    """

    time_range_parameters = {
        "start_date": data_request.time_range.start_date,
        "end_date": data_request.time_range.end_date,
    }
    grouped_query_parameters = {
        **time_range_parameters,
        "result_limit": data_request.result_limit,
    }

    prepared_dataframe = connection.execute(
        grouped_query,
        grouped_query_parameters,
    ).df()
    quality_counts = connection.execute(quality_query, time_range_parameters).fetchone()
    if quality_counts is None:
        missing_metric_count = 0
        missing_dimension_count = 0
    else:
        missing_metric_count = int(quality_counts[0] or 0)
        missing_dimension_count = int(quality_counts[1] or 0)

    return contracts.PreparedData(
        request=data_request,
        data=prepared_dataframe,
        quality_notes=_quality_notes(
            metric_column=metric_column,
            dimension_label=data_request.dimension.label,
            missing_metric_count=missing_metric_count,
            missing_dimension_count=missing_dimension_count,
        ),
    )


def _sum_metric_column(metric_expression: str) -> str:
    expression = metric_expression.strip()
    if not expression.startswith("sum(") or not expression.endswith(")"):
        raise ValueError(f"Unsupported metric expression: {metric_expression}")
    return expression.removeprefix("sum(").removesuffix(")").strip()


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

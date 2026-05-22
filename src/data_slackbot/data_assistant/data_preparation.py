"""Prepared Data step for Data Assistant revenue by region."""

from __future__ import annotations

import decimal

import duckdb

import data_slackbot.data_assistant.workflow.contracts as contracts


def prepare_data(
    data_request: contracts.DataRequest,
    connection: duckdb.DuckDBPyConnection,
) -> contracts.PreparedData:
    """Produce bounded grouped Prepared Data from local DuckDB rows."""
    metric_column = _sum_metric_column(data_request.metric_expression)
    grouped_query = f"""
        select
            {_quote_identifier(data_request.dimension_column)} as region,
            sum({_quote_identifier(metric_column)}) as total_revenue
        from {_quote_identifier(data_request.table_id)}
        where {_quote_identifier(data_request.date_column)} >= ?
          and {_quote_identifier(data_request.date_column)} <= ?
        group by {_quote_identifier(data_request.dimension_column)}
        order by total_revenue desc, region asc
        limit ?
    """
    count_query = f"""
        select count(*)
        from {_quote_identifier(data_request.table_id)}
        where {_quote_identifier(data_request.date_column)} >= ?
          and {_quote_identifier(data_request.date_column)} <= ?
    """
    grouped_results = connection.execute(
        grouped_query,
        (
            data_request.time_range.start_date,
            data_request.time_range.end_date,
            data_request.result_limit,
        ),
    ).fetchall()
    source_row_count = connection.execute(
        count_query,
        (
            data_request.time_range.start_date,
            data_request.time_range.end_date,
        ),
    ).fetchone()

    return contracts.PreparedData(
        request=data_request,
        rows=tuple(
            contracts.PreparedRevenueByRegion(
                region=_str_result(region),
                total_revenue=_decimal_result(total_revenue),
            )
            for region, total_revenue in grouped_results
        ),
        source_row_count=_int_result(source_row_count[0] if source_row_count else 0),
    )


def _sum_metric_column(expression: str) -> str:
    normalized_expression = expression.strip().casefold()
    if not normalized_expression.startswith("sum(") or not expression.endswith(")"):
        msg = f"Unsupported metric expression: {expression}"
        raise ValueError(msg)
    column = expression.strip()[4:-1].strip()
    if not column:
        msg = f"Unsupported metric expression: {expression}"
        raise ValueError(msg)
    return column


def _quote_identifier(identifier: str) -> str:
    escaped_identifier = identifier.replace('"', '""')
    return f'"{escaped_identifier}"'


def _str_result(value: object) -> str:
    if not isinstance(value, str):
        msg = f"Expected string query result, got {type(value).__name__}"
        raise TypeError(msg)
    return value


def _decimal_result(value: object) -> decimal.Decimal:
    if isinstance(value, decimal.Decimal):
        return value
    if isinstance(value, int | float | str):
        return decimal.Decimal(str(value))
    msg = f"Expected decimal query result, got {type(value).__name__}"
    raise TypeError(msg)


def _int_result(value: object) -> int:
    if not isinstance(value, int):
        msg = f"Expected integer query result, got {type(value).__name__}"
        raise TypeError(msg)
    return value

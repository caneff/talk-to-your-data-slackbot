"""Prepared Data step for Data Assistant revenue by region."""

from __future__ import annotations

import typing

import duckdb

import data_assistant.workflow.contracts as contracts


def prepare_data(
    data_request: contracts.DataRequest,
    connection: duckdb.DuckDBPyConnection,
) -> contracts.PreparedData:
    """Produce bounded grouped Prepared Data from local DuckDB rows."""
    grouped_query = f"""
        with filtered_rows as (
            select *
            from {data_request.table.table_id}
            where {data_request.table.date_column} >= $start_date
              and {data_request.table.date_column} <= $end_date
        )
        select
            {data_request.dimension.column} as dimension_value,
            {data_request.metric.expression} as metric_value,
            (select count(*) from filtered_rows) as source_row_count
        from filtered_rows
        group by {data_request.dimension.column}
        order by metric_value desc, dimension_value asc
        limit $result_limit
    """
    query_parameters = {
        "start_date": data_request.time_range.start_date,
        "end_date": data_request.time_range.end_date,
        "result_limit": data_request.result_limit,
    }
    prepared_dataframe = connection.execute(
        grouped_query,
        query_parameters,
    ).df()
    source_row_count = (
        int(typing.cast(int, prepared_dataframe.loc[0, "source_row_count"]))
        if not prepared_dataframe.empty
        else 0
    )
    prepared_dataframe = prepared_dataframe.loc[
        :,
        ["dimension_value", "metric_value"],
    ]

    return contracts.PreparedData(
        request=data_request,
        data=prepared_dataframe,
        source_row_count=source_row_count,
    )

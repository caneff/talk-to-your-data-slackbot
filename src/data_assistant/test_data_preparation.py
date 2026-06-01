import dataclasses
import datetime

import pandas as pd
import pandas.testing as pd_testing

import data_assistant.data_preparation as data_preparation
import data_assistant.local_duckdb_fixture as local_duckdb_fixture
import data_assistant.semantic_layer.schema as schema
import data_assistant.workflow.contracts as contracts


def test_prepared_data_contains_bounded_grouped_revenue_results(
    data_request: contracts.DataRequest,
    connect_orders: local_duckdb_fixture.OrdersConnector,
) -> None:
    order_rows = (
        ("2026-01-03", "North", "1200.00"),
        ("2026-01-08", "South", "850.00"),
        ("2026-01-15", "West", "1600.00"),
        ("2026-01-22", "North", "300.00"),
        ("2026-01-28", "East", "950.00"),
        ("2026-02-01", "West", "9999.00"),
    )
    with connect_orders(order_rows) as connection:
        prepared_data = data_preparation.prepare_data(data_request, connection)

    assert data_request.result_limit == 10
    assert len(prepared_data.data) <= data_request.result_limit
    expected_data = pd.DataFrame(
        {
            "dimension_value": ("West", "North", "East", "South"),
            "metric_value": (1600.0, 1500.0, 950.0, 850.0),
        },
    )
    pd_testing.assert_frame_equal(prepared_data.data, expected_data)


def test_prepared_data_returns_empty_grouped_result_when_no_rows_match(
    data_request: contracts.DataRequest,
    connect_orders: local_duckdb_fixture.OrdersConnector,
) -> None:
    order_date_field = data_request.filter_operations[0].field
    data_request = dataclasses.replace(
        data_request,
        filter_operations=(
            contracts.ResolvedSemanticFieldOperation(
                operation=schema.FieldOperation.RANGE_FILTER,
                field=order_date_field,
                lower=datetime.date(2025, 10, 1),
                upper=datetime.date(2025, 12, 31),
            ),
        ),
    )
    order_rows = (
        ("2026-01-03", "North", "1200.00"),
        ("2026-01-08", "South", "850.00"),
    )
    with connect_orders(order_rows) as connection:
        prepared_data = data_preparation.prepare_data(data_request, connection)

    expected_data = pd.DataFrame(
        {
            "dimension_value": pd.Series(dtype="object"),
            "metric_value": pd.Series(dtype="float64"),
        },
    )
    pd_testing.assert_frame_equal(prepared_data.data, expected_data)
    assert prepared_data.quality_notes == ("No rows matched the request filters.",)


def test_prepared_data_records_quality_notes_after_time_filtering(
    data_request: contracts.DataRequest,
    connect_orders: local_duckdb_fixture.OrdersConnector,
) -> None:
    order_rows = (
        ("2026-01-03", "North", "100.00"),
        ("2026-01-08", None, "200.00"),
        ("2026-01-15", "", "300.00"),
        ("2026-01-22", " ", "400.00"),
        ("2026-01-28", "South", None),
        ("2026-02-01", None, None),
    )
    with connect_orders(order_rows) as connection:
        prepared_data = data_preparation.prepare_data(data_request, connection)

    expected_data = pd.DataFrame(
        {
            "dimension_value": ("Unknown", "North"),
            "metric_value": (900.0, 100.0),
        },
    )
    pd_testing.assert_frame_equal(prepared_data.data, expected_data)
    assert prepared_data.quality_notes == (
        "1 row excluded because revenue was missing.",
        "3 rows grouped under Unknown because region was missing.",
    )


def test_prepared_data_uses_metric_source_column_for_missing_values(
    data_request: contracts.DataRequest,
    connect_orders: local_duckdb_fixture.OrdersConnector,
) -> None:
    data_request = dataclasses.replace(
        data_request,
        metric=schema.Metric(
            metric_id="total_revenue",
            label="total revenue",
            expression="sum(revenue * 1)",
            source_column="revenue",
            kind=schema.MetricKind.MONEY,
        ),
    )
    order_rows = (
        ("2026-01-03", "North", "100.00"),
        ("2026-01-08", "North", None),
    )
    with connect_orders(order_rows) as connection:
        prepared_data = data_preparation.prepare_data(data_request, connection)

    expected_data = pd.DataFrame(
        {
            "dimension_value": ("North",),
            "metric_value": (100.0,),
        },
    )
    pd_testing.assert_frame_equal(prepared_data.data, expected_data)
    assert prepared_data.quality_notes == (
        "1 row excluded because revenue was missing.",
    )


def test_prepared_data_applies_include_filter_with_parameters(
    data_request: contracts.DataRequest,
    connect_orders: local_duckdb_fixture.OrdersConnector,
) -> None:
    region_field = data_request.group_by_fields[0]
    data_request = dataclasses.replace(
        data_request,
        filter_operations=(
            contracts.ResolvedSemanticFieldOperation(
                operation=schema.FieldOperation.INCLUDE_FILTER,
                field=region_field,
                values=("North",),
            ),
        ),
    )
    order_rows = (
        ("2026-01-03", "North", "1200.00"),
        ("2026-01-08", "South", "850.00"),
        ("2026-01-22", "North", "300.00"),
    )
    with connect_orders(order_rows) as connection:
        prepared_data = data_preparation.prepare_data(data_request, connection)

    expected_data = pd.DataFrame(
        {
            "dimension_value": ("North",),
            "metric_value": (1500.0,),
        },
    )
    pd_testing.assert_frame_equal(prepared_data.data, expected_data)


def test_prepared_data_applies_exclude_filter_with_parameters(
    data_request: contracts.DataRequest,
    connect_orders: local_duckdb_fixture.OrdersConnector,
) -> None:
    region_field = data_request.group_by_fields[0]
    data_request = dataclasses.replace(
        data_request,
        filter_operations=(
            contracts.ResolvedSemanticFieldOperation(
                operation=schema.FieldOperation.EXCLUDE_FILTER,
                field=region_field,
                values=("South",),
            ),
        ),
    )
    order_rows = (
        ("2026-01-03", "North", "1200.00"),
        ("2026-01-08", "South", "850.00"),
        ("2026-01-22", "North", "300.00"),
    )
    with connect_orders(order_rows) as connection:
        prepared_data = data_preparation.prepare_data(data_request, connection)

    expected_data = pd.DataFrame(
        {
            "dimension_value": ("North",),
            "metric_value": (1500.0,),
        },
    )
    pd_testing.assert_frame_equal(prepared_data.data, expected_data)


def test_prepared_data_supports_scalar_aggregate_without_group_by(
    data_request: contracts.DataRequest,
    connect_orders: local_duckdb_fixture.OrdersConnector,
) -> None:
    data_request = dataclasses.replace(data_request, group_by_fields=())
    order_rows = (
        ("2026-01-03", "North", "1200.00"),
        ("2026-01-08", "South", "850.00"),
        ("2026-01-22", "North", "300.00"),
    )
    with connect_orders(order_rows) as connection:
        prepared_data = data_preparation.prepare_data(data_request, connection)

    expected_data = pd.DataFrame(
        {
            "dimension_value": ("All",),
            "metric_value": (2350.0,),
        },
    )
    pd_testing.assert_frame_equal(prepared_data.data, expected_data)


def test_prepared_data_contains_all_time_grouped_revenue_results(
    data_request: contracts.DataRequest,
    connect_orders: local_duckdb_fixture.OrdersConnector,
) -> None:
    data_request = dataclasses.replace(data_request, filter_operations=())
    order_rows = (
        ("2026-01-03", "North", "1200.00"),
        ("2026-01-08", "South", "850.00"),
        ("2026-01-15", "West", "1600.00"),
        ("2026-01-22", "North", "300.00"),
        ("2026-01-28", "East", "950.00"),
        ("2026-02-01", "West", "9999.00"),
    )
    with connect_orders(order_rows) as connection:
        prepared_data = data_preparation.prepare_data(data_request, connection)

    expected_data = pd.DataFrame(
        {
            "dimension_value": ("West", "North", "East", "South"),
            "metric_value": (11599.0, 1500.0, 950.0, 850.0),
        },
    )
    pd_testing.assert_frame_equal(prepared_data.data, expected_data)


def test_prepared_data_supports_scalar_all_time_aggregate_without_filters(
    data_request: contracts.DataRequest,
    connect_orders: local_duckdb_fixture.OrdersConnector,
) -> None:
    data_request = dataclasses.replace(
        data_request,
        group_by_fields=(),
        filter_operations=(),
    )
    order_rows = (
        ("2026-01-03", "North", "1200.00"),
        ("2026-01-08", "South", "850.00"),
        ("2026-01-22", "North", "300.00"),
        ("2026-02-01", "West", "9999.00"),
    )
    with connect_orders(order_rows) as connection:
        prepared_data = data_preparation.prepare_data(data_request, connection)

    expected_data = pd.DataFrame(
        {
            "dimension_value": ("All",),
            "metric_value": (12349.0,),
        },
    )
    pd_testing.assert_frame_equal(prepared_data.data, expected_data)

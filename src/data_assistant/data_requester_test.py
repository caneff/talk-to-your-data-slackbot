import data_assistant.workflow.contracts as contracts


def test_data_request_asks_for_total_revenue_grouped_by_region(
    data_request: contracts.DataRequest,
) -> None:
    assert data_request.dataset.dataset_id == "retail_ops"
    assert data_request.table.table_id == "orders"
    assert data_request.metric.metric_id == "total_revenue"
    assert data_request.metric.label == "total revenue"
    assert data_request.metric.expression == "sum(revenue)"
    assert data_request.metric.source_column == "revenue"
    assert data_request.group_by_field is not None
    assert data_request.group_by_field.field_id == "region"
    assert data_request.group_by_field.label == "region"
    assert data_request.group_by_field.source_column == "region"
    assert data_request.filter_labels == ("order date >= 2026-01-01 and <= 2026-01-31",)
    assert data_request.output_shape == "total revenue grouped by region"


def test_data_request_selects_orders_when_retail_has_customer_metadata(
    data_request: contracts.DataRequest,
) -> None:
    assert data_request.dataset.tables == ("orders", "customers")
    assert data_request.table.table_id == "orders"
    assert data_request.metric.metric_id == "total_revenue"
    assert data_request.group_by_field is not None
    assert data_request.group_by_field.field_id == "region"


def test_data_request_carries_calendar_grouping_separately_from_group_by_field(
    data_request: contracts.DataRequest,
) -> None:
    order_date_field = data_request.field_filters[0].field
    calendar_request = contracts.DataRequest(
        dataset=data_request.dataset,
        table=data_request.table,
        metric=data_request.metric,
        group_by_field=None,
        field_filters=data_request.field_filters,
        output_shape="total revenue grouped by order date month",
        result_limit=data_request.result_limit,
        calendar_grouping=contracts.CalendarGrouping(
            field=order_date_field,
            grain=contracts.CalendarGrain.MONTH,
        ),
    )

    assert calendar_request.group_by_field is None
    assert calendar_request.calendar_grouping is not None
    assert calendar_request.calendar_grouping.field.field_id == "order_date"
    assert calendar_request.output_shape == "total revenue grouped by order date month"

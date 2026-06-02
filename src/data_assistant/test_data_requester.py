import data_assistant.workflow.contracts as contracts


def test_data_request_asks_for_total_revenue_grouped_by_region(
    data_request: contracts.DataRequest,
) -> None:
    assert data_request.dataset.dataset_id == "commerce"
    assert data_request.table.table_id == "orders"
    assert data_request.metric.metric_id == "total_revenue"
    assert data_request.metric.label == "total revenue"
    assert data_request.metric.expression == "sum(revenue)"
    assert data_request.metric.source_column == "revenue"
    assert data_request.group_by_fields[0].field_id == "region"
    assert data_request.group_by_fields[0].label == "region"
    assert data_request.group_by_fields[0].source_column == "region"
    assert data_request.filter_labels == ("order date >= 2026-01-01 and <= 2026-01-31",)
    assert data_request.output_shape == "total revenue grouped by region"


def test_data_request_selects_orders_when_commerce_has_customer_metadata(
    data_request: contracts.DataRequest,
) -> None:
    assert data_request.dataset.tables == ("orders", "customers")
    assert data_request.table.table_id == "orders"
    assert data_request.metric.metric_id == "total_revenue"
    assert data_request.group_by_fields[0].field_id == "region"

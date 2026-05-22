from data_slackbot.clean_commerce_spine import contracts


def test_data_request_asks_for_total_revenue_grouped_by_region(
    data_request: contracts.DataRequest,
) -> None:
    assert data_request.curated_dataset_id == "commerce"
    assert data_request.table_id == "orders"
    assert data_request.metric_id == "total_revenue"
    assert data_request.metric_label == "total revenue"
    assert data_request.metric_expression == "sum(revenue)"
    assert data_request.dimension_id == "region"
    assert data_request.dimension_label == "region"
    assert data_request.dimension_column == "region"
    assert data_request.date_column == "order_date"
    assert data_request.time_range.label == "January 2026"
    assert data_request.filters == ()
    assert data_request.output_shape == "total revenue grouped by region"

from talk_to_your_data_slackbot.clean_commerce_spine import contracts


def test_data_request_asks_for_total_revenue_grouped_by_region(
    data_request: contracts.DataRequest,
) -> None:
    assert data_request.curated_dataset_id == "commerce"
    assert data_request.selected_tables == ("orders",)
    assert data_request.metric == "total revenue"
    assert data_request.group_by == ("region",)
    assert data_request.time_range.label == "January 2026"
    assert data_request.filters == ()
    assert data_request.output_shape == "total revenue grouped by region"

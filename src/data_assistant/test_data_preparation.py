import decimal

import data_assistant.workflow.contracts as contracts


def test_prepared_data_contains_bounded_grouped_revenue_results(
    data_request: contracts.DataRequest,
    prepared_data: contracts.PreparedData,
) -> None:
    assert data_request.result_limit == 10
    assert len(prepared_data.rows) <= data_request.result_limit
    assert prepared_data.source_row_count == 5
    assert prepared_data.rows == (
        contracts.PreparedRevenueByRegion(
            region="West",
            total_revenue=decimal.Decimal("1600.00"),
        ),
        contracts.PreparedRevenueByRegion(
            region="North",
            total_revenue=decimal.Decimal("1500.00"),
        ),
        contracts.PreparedRevenueByRegion(
            region="East",
            total_revenue=decimal.Decimal("950.00"),
        ),
        contracts.PreparedRevenueByRegion(
            region="South",
            total_revenue=decimal.Decimal("850.00"),
        ),
    )

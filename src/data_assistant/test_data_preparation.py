import pandas as pd
import pandas.testing as pd_testing

import data_assistant.data_preparation as data_preparation
import data_assistant.testing_support as testing_support
import data_assistant.workflow.contracts as contracts


def test_prepared_data_contains_bounded_grouped_revenue_results(
    data_request: contracts.DataRequest,
    connect_orders: testing_support.OrdersConnector,
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

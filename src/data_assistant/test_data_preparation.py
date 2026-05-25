import pandas as pd
import pandas.testing as pd_testing

import data_assistant.workflow.contracts as contracts


def test_prepared_data_contains_bounded_grouped_revenue_results(
    data_request: contracts.DataRequest,
    prepared_data: contracts.PreparedData,
) -> None:
    assert data_request.result_limit == 10
    assert len(prepared_data.data) <= data_request.result_limit
    assert prepared_data.source_row_count == 5
    expected_data = pd.DataFrame(
        {
            "dimension_value": ("West", "North", "East", "South"),
            "metric_value": (1600.0, 1500.0, 950.0, 850.0),
        },
    )
    pd_testing.assert_frame_equal(prepared_data.data, expected_data)

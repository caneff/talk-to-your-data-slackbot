import pandas.testing as pd_testing

import data_assistant.testing_support as testing_support
import data_assistant.workflow.contracts as contracts
import data_assistant.workflow.runner as workflow_runner


def test_reasoning_layer_produces_answer_draft_from_prepared_data(
    canonical_question: str,
    connect_orders: testing_support.OrdersConnector,
) -> None:
    order_rows = (
        ("2026-01-03", "North", "1200.00"),
        ("2026-01-08", "South", "850.00"),
        ("2026-01-15", "West", "1600.00"),
        ("2026-01-20", " ", "250.00"),
        ("2026-01-22", "North", "300.00"),
        ("2026-01-28", "East", "950.00"),
        ("2026-01-29", "East", None),
        ("2026-02-01", None, None),
    )
    with connect_orders(order_rows) as connection:
        run = workflow_runner.run_data_assistant(
            connection,
            canonical_question,
        )

    assert isinstance(run, contracts.DataAssistantRun)
    assert run.answer_draft.summary == (
        "Total revenue in January 2026 was $5,150.00, grouped across 5 regions."
    )
    pd_testing.assert_frame_equal(run.answer_draft.key_data, run.prepared_data.data)
    assert run.answer_draft.datasets_used == ("Commerce Revenue",)
    assert run.answer_draft.dataset_tables_used == ("orders",)
    assert run.answer_draft.time_range == "January 2026"
    assert run.answer_draft.filters == ()
    assert run.answer_draft.freshness == (
        "Commerce order data refreshed through 2026-01-31."
    )
    assert run.answer_draft.caveats == (
        "1 row excluded because revenue was missing.",
        "1 row grouped under Unknown because region was missing.",
    )

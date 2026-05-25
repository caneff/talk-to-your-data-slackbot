import data_assistant.testing_support as testing_support
import data_assistant.workflow.contracts as contracts
import data_assistant.workflow.runner as workflow_runner


def test_response_composer_returns_plain_text_with_trust_summary(
    canonical_question: str,
    connect_orders: testing_support.OrdersConnector,
) -> None:
    order_rows = (
        ("2026-01-03", "North", "1200.00"),
        ("2026-01-08", "South", "850.00"),
        ("2026-01-15", "West", "1600.00"),
        ("2026-01-22", "North", "300.00"),
        ("2026-01-28", "East", "950.00"),
    )
    with connect_orders(order_rows) as connection:
        run = workflow_runner.run_data_assistant(
            connection,
            canonical_question,
        )

    assert isinstance(run, contracts.DataAssistantRun)
    assert run.final_response.text == (
        "Total revenue in January 2026 was $4,900.00, grouped across 4 regions."
        "\n\n"
        "- West: $1,600.00\n"
        "- North: $1,500.00\n"
        "- East: $950.00\n"
        "- South: $850.00"
        "\n\n"
        "Trust Summary: Curated Dataset: Commerce Revenue. "
        "Dataset Table: orders. "
        "Time range: January 2026. "
        "Filters: none. "
        "Caveats: Commerce order data refreshed through 2026-01-31."
    )
    assert run.final_response.trust_summary in run.final_response.text
    assert "customers" not in run.final_response.trust_summary

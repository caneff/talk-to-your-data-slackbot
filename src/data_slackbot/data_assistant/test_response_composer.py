import duckdb

import data_slackbot.data_assistant.workflow.contracts as contracts
import data_slackbot.data_assistant.workflow.runner as workflow_runner


def test_response_composer_returns_plain_text_with_trust_summary(
    commerce_connection: duckdb.DuckDBPyConnection,
    canonical_question: str,
) -> None:
    run = workflow_runner.run_data_assistant(
        commerce_connection,
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
        "Time range: January 2026. "
        "Filters: none. "
        "Caveats: Commerce order data refreshed through 2026-01-31."
    )
    assert run.final_response.trust_summary in run.final_response.text

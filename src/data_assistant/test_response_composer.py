import data_assistant.response_composer as response_composer
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
    assert run.final_response.text == (
        "Total revenue in January 2026 was $5,150.00, grouped across 5 regions."
        "\n\n"
        "- West: $1,600.00\n"
        "- North: $1,500.00\n"
        "- East: $950.00\n"
        "- South: $850.00\n"
        "- Unknown: $250.00"
        "\n\n"
        "Trust Summary: Curated Dataset: Commerce Revenue. "
        "Dataset Table: orders. "
        "Time range: January 2026. "
        "Filters: none. "
        "Caveats: Commerce order data refreshed through 2026-01-31. "
        "1 row excluded because revenue was missing. "
        "1 row grouped under Unknown because region was missing."
    )
    assert run.final_response.trust_summary in run.final_response.text
    assert "customers" not in run.final_response.trust_summary


def test_response_composer_returns_final_response_for_non_answer() -> None:
    response = response_composer.compose_non_answer_response(
        contracts.NonAnswer(
            stage="question_interpreter",
            reason="User-provided CSV files are not supported data sources.",
            unresolved_ambiguities=("unsupported data",),
            next_step=(
                "Ask about an approved Curated Dataset in the Semantic Layer "
                "instead."
            ),
        )
    )

    assert response == contracts.FinalResponse(
        text=(
            "I cannot answer safely because user-provided CSV files are not "
            "supported data sources.\n\n"
            "Next step: Ask about an approved Curated Dataset in the "
            "Semantic Layer instead."
        ),
        trust_summary=(
            "Trust Summary: Returned a Non-Answer Response from "
            "question_interpreter."
        ),
    )

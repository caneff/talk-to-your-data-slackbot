import data_assistant.testing_support as testing_support
import data_assistant.workflow.contracts as contracts
import data_assistant.workflow.runner as workflow_runner


def test_data_assistant_runs_end_to_end(
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
    assert run.question_frame.unresolved_ambiguities == ()
    assert len(run.dataset_selection.selected_datasets) == 1
    assert run.data_request.metric.label == "total revenue"
    assert run.prepared_data.data.loc[0, "dimension_value"] == "West"
    assert run.prepared_data.quality_notes == (
        "1 row excluded because revenue was missing.",
        "1 row grouped under Unknown because region was missing.",
    )
    assert "- Unknown: $250.00" in run.final_response.text
    assert "$5,150.00" in run.final_response.text
    assert "1 row excluded because revenue was missing." in (
        run.final_response.trust_summary
    )
    assert "1 row grouped under Unknown because region was missing." in (
        run.final_response.trust_summary
    )
    assert "Trust Summary:" in run.final_response.text


def test_data_assistant_short_circuits_question_ambiguity(
    connect_orders: testing_support.OrdersConnector,
) -> None:
    order_rows = (
        ("2026-01-03", "North", "1200.00"),
    )
    with connect_orders(order_rows) as connection:
        result = workflow_runner.run_data_assistant(
            connection,
            "What was total revenue by region?",
        )

    assert result == contracts.NonAnswer(
        stage="question_interpreter",
        reason="The Data Question is missing required interpretation details.",
        unresolved_ambiguities=("time range",),
        next_step="Ask a clarification question before selecting data.",
    )

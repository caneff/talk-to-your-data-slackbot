import pytest

import data_assistant.data_preparation as data_preparation
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
        ("2026-01-22", "North", "300.00"),
        ("2026-01-28", "East", "950.00"),
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


def test_data_assistant_short_circuits_unsupported_question_before_preparing_data(
    monkeypatch: pytest.MonkeyPatch,
    connect_orders: testing_support.OrdersConnector,
) -> None:
    def fail_prepare_data(
        data_request: contracts.DataRequest,
        connection: object,
    ) -> contracts.PreparedData:
        raise AssertionError("prepare_data should not be called")

    monkeypatch.setattr(data_preparation, "prepare_data", fail_prepare_data)
    order_rows = (
        ("2026-01-03", "North", "1200.00"),
    )

    with connect_orders(order_rows) as connection:
        result = workflow_runner.run_data_assistant(
            connection,
            "Can you forecast revenue for next quarter?",
        )

    assert result == contracts.NonAnswer(
        stage="question_interpreter",
        reason=(
            "The Data Assistant currently supports total revenue by region "
            "for one month."
        ),
        unresolved_ambiguities=("supported shape",),
        next_step="Ask: What was total revenue by region in January 2026?",
    )

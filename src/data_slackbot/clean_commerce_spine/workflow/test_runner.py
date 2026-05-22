import duckdb

import data_slackbot.clean_commerce_spine.workflow.contracts as contracts
import data_slackbot.clean_commerce_spine.workflow.runner as workflow_runner


def test_clean_commerce_spine_runs_end_to_end(
    commerce_connection: duckdb.DuckDBPyConnection,
    canonical_question: str,
) -> None:
    run = workflow_runner.run_clean_commerce_spine(
        commerce_connection,
        canonical_question,
    )

    assert isinstance(run, contracts.DataAssistantRun)
    assert run.question_frame.unresolved_ambiguities == ()
    assert len(run.dataset_selection.selected_datasets) == 1
    assert run.data_request.metric_label == "total revenue"
    assert run.prepared_data.rows[0].region == "West"
    assert "Trust Summary:" in run.final_response.text


def test_clean_commerce_spine_short_circuits_question_ambiguity(
    commerce_connection: duckdb.DuckDBPyConnection,
) -> None:
    result = workflow_runner.run_clean_commerce_spine(
        commerce_connection,
        "What was total revenue by region?",
    )

    assert result == contracts.NonAnswer(
        stage="question_interpreter",
        reason="The Data Question is missing required interpretation details.",
        unresolved_ambiguities=("time range",),
        next_step="Ask a clarification question before selecting data.",
    )

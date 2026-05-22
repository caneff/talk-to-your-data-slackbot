import duckdb

import data_assistant.workflow.contracts as contracts
import data_assistant.workflow.runner as workflow_runner


def test_reasoning_layer_produces_answer_draft_from_prepared_data(
    commerce_connection: duckdb.DuckDBPyConnection,
    canonical_question: str,
) -> None:
    run = workflow_runner.run_data_assistant(
        commerce_connection,
        canonical_question,
    )

    assert isinstance(run, contracts.DataAssistantRun)
    assert run.answer_draft.summary == (
        "Total revenue in January 2026 was $4,900.00, grouped across 4 regions."
    )
    assert run.answer_draft.key_numbers == run.prepared_data.rows
    assert run.answer_draft.datasets_used == ("Commerce Revenue",)
    assert run.answer_draft.time_range == "January 2026"
    assert run.answer_draft.filters == ()
    assert run.answer_draft.caveats == (
        "Commerce order data refreshed through 2026-01-31.",
    )

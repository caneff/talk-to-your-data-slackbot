from data_slackbot.clean_commerce_spine import workflow


def test_clean_commerce_spine_runs_end_to_end() -> None:
    run = workflow.run_clean_commerce_spine()

    assert run.question_frame.unresolved_ambiguities == ()
    assert len(run.dataset_selection.selected_datasets) == 1
    assert run.data_request.metric == "total revenue"
    assert run.prepared_data.rows[0].region == "West"
    assert "Trust Summary:" in run.final_response.text

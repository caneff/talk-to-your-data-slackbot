from data_slackbot.clean_commerce_spine import workflow


def test_reasoning_layer_produces_answer_draft_from_prepared_data() -> None:
    run = workflow.run_clean_commerce_spine()

    assert run.answer_draft.summary == (
        "Total revenue in January 2026 was $4,900.00, grouped across 4 regions."
    )
    assert run.answer_draft.key_numbers == run.prepared_data.rows
    assert run.answer_draft.datasets_used == ("Commerce Revenue",)
    assert run.answer_draft.time_range == "January 2026"
    assert run.answer_draft.filters == ()
    assert run.answer_draft.caveats == ("Clean fixture rows only.",)

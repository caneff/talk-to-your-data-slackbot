from talk_to_your_data_slackbot.clean_commerce_spine import workflow


def test_response_composer_returns_plain_text_with_trust_summary() -> None:
    run = workflow.run_clean_commerce_spine()

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
        "Caveats: Clean fixture rows only."
    )
    assert run.final_response.trust_summary in run.final_response.text

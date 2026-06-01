import data_assistant.reasoning_layer as reasoning_layer
import data_assistant.reasoning_layer.narrative_cases as narrative_cases
import data_assistant.semantic_layer.schema as schema


def test_reasoning_layer_produces_answer_draft_from_prepared_data() -> None:
    prepared_data = narrative_cases.prepared_revenue_by_region()

    answer_draft = reasoning_layer.draft_answer(prepared_data)

    assert answer_draft.summary == (
        "Total revenue in 2026-01-01 through 2026-01-31 was $5,150.00, "
        "grouped across 5 regions."
    )
    assert answer_draft.key_data is prepared_data.data
    assert answer_draft.datasets_used == ("Commerce",)
    assert answer_draft.dataset_tables_used == ("orders",)
    assert answer_draft.metric_kind == schema.MetricKind.MONEY
    assert answer_draft.time_range == "2026-01-01 through 2026-01-31"
    assert answer_draft.filters == ("order date >= 2026-01-01 and <= 2026-01-31",)
    assert answer_draft.freshness == (
        "Commerce order data refreshed through 2026-01-31."
    )
    assert answer_draft.caveats == (
        "1 row excluded because revenue was missing.",
        "1 row grouped under Unknown because region was missing.",
    )


def test_reasoning_layer_formats_count_summary_and_carries_metric_kind() -> None:
    prepared_data = narrative_cases.prepared_customer_count()

    answer_draft = reasoning_layer.draft_answer(prepared_data)

    assert answer_draft.summary == (
        "Customer count in 2026-01-01 through 2026-01-31 was 1,234."
    )
    assert answer_draft.metric_kind == schema.MetricKind.COUNT


def test_reasoning_layer_labels_all_time_when_no_date_filter_exists() -> None:
    prepared_data = narrative_cases.prepared_revenue_by_region(all_time=True)

    answer_draft = reasoning_layer.draft_answer(prepared_data)

    assert answer_draft.summary == (
        "Total revenue in all available data was $5,150.00, grouped across 5 regions."
    )
    assert answer_draft.time_range == "all available data"
    assert answer_draft.filters == ()

"""Behavior tests for grounded narration in the Reasoning Layer (ADR-0012)."""

import dataclasses
import datetime

import pydantic

import data_assistant.reasoning_layer as reasoning_layer
import data_assistant.reasoning_layer.narrative_cases as narrative_cases
import data_assistant.reasoning_layer.testing_support as reasoning_support
import data_assistant.workflow.contracts as contracts


def test_compute_slot_values_ranks_grouped_prepared_data() -> None:
    slot_values = reasoning_layer.compute_slot_values(
        narrative_cases.prepared_revenue_by_region()
    )

    assert slot_values == {
        "metric": "Total revenue",
        "time_range": "January 2026",
        "metric_total": "$5,150.00",
        "dimension": "regions",
        "dimension_count": 5,
        "top_dimension": "West",
        "top_value": "$1,600.00",
    }


def test_compute_slot_values_for_scalar_prepared_data_has_empty_ranking() -> None:
    slot_values = reasoning_layer.compute_slot_values(
        narrative_cases.prepared_customer_count()
    )

    assert slot_values == {
        "metric": "Customer count",
        "time_range": "January 2026",
        "metric_total": "1,234",
        "dimension": "",
        "dimension_count": 1,
        "top_dimension": "",
        "top_value": "",
    }


def test_compute_slot_values_for_empty_grouped_data_has_empty_ranking() -> None:
    slot_values = reasoning_layer.compute_slot_values(
        narrative_cases.prepared_empty_revenue_by_region()
    )

    assert slot_values == {
        "metric": "Total revenue",
        "time_range": "Q4 2025",
        "metric_total": "$0.00",
        "dimension": "regions",
        "dimension_count": 0,
        "top_dimension": "",
        "top_value": "",
    }


def test_compute_slot_values_formats_exact_calendar_quarter() -> None:
    prepared_data = narrative_cases.prepared_revenue_by_region()
    quarter_request = dataclasses.replace(
        prepared_data.request,
        field_filters=(
            contracts.RangeFilter(
                field=prepared_data.request.field_filters[0].field,
                lower=datetime.date(2026, 1, 1),
                upper=datetime.date(2026, 3, 31),
            ),
        ),
    )

    slot_values = reasoning_layer.compute_slot_values(
        dataclasses.replace(prepared_data, request=quarter_request)
    )

    assert slot_values["time_range"] == "Q1 2026"


def test_compute_slot_values_formats_exact_calendar_year() -> None:
    prepared_data = narrative_cases.prepared_revenue_by_region()
    year_request = dataclasses.replace(
        prepared_data.request,
        field_filters=(
            contracts.RangeFilter(
                field=prepared_data.request.field_filters[0].field,
                lower=datetime.date(2026, 1, 1),
                upper=datetime.date(2026, 12, 31),
            ),
        ),
    )

    slot_values = reasoning_layer.compute_slot_values(
        dataclasses.replace(prepared_data, request=year_request)
    )

    assert slot_values["time_range"] == "2026"


def test_compute_slot_values_formats_non_period_closed_ranges_readably() -> None:
    prepared_data = narrative_cases.prepared_revenue_by_region()
    closed_range_request = dataclasses.replace(
        prepared_data.request,
        field_filters=(
            contracts.RangeFilter(
                field=prepared_data.request.field_filters[0].field,
                lower=datetime.date(2026, 1, 1),
                upper=datetime.date(2026, 3, 15),
            ),
        ),
    )

    slot_values = reasoning_layer.compute_slot_values(
        dataclasses.replace(prepared_data, request=closed_range_request)
    )

    assert slot_values["time_range"] == "Jan 1 - Mar 15, 2026"


def test_compute_slot_values_formats_half_open_ranges_readably() -> None:
    prepared_data = narrative_cases.prepared_revenue_by_region()
    half_open_request = dataclasses.replace(
        prepared_data.request,
        field_filters=(
            contracts.RangeFilter(
                field=prepared_data.request.field_filters[0].field,
                lower=datetime.date(2026, 1, 1),
                upper=None,
            ),
        ),
    )

    slot_values = reasoning_layer.compute_slot_values(
        dataclasses.replace(prepared_data, request=half_open_request)
    )

    assert slot_values["time_range"] == "the period from Jan 1, 2026"


def test_compute_slot_values_formats_upper_only_half_open_range_readably() -> None:
    prepared_data = narrative_cases.prepared_revenue_by_region()
    half_open_request = dataclasses.replace(
        prepared_data.request,
        field_filters=(
            contracts.RangeFilter(
                field=prepared_data.request.field_filters[0].field,
                lower=None,
                upper=datetime.date(2023, 12, 31),
            ),
        ),
    )

    slot_values = reasoning_layer.compute_slot_values(
        dataclasses.replace(prepared_data, request=half_open_request)
    )

    assert slot_values["time_range"] == "the period through Dec 31, 2023"


def test_template_summary_joins_open_ended_time_range_without_double_preposition() -> (
    None
):
    prepared_data = narrative_cases.prepared_revenue_by_region()
    open_ended_request = dataclasses.replace(
        prepared_data.request,
        field_filters=(
            contracts.RangeFilter(
                field=prepared_data.request.field_filters[0].field,
                lower=None,
                upper=datetime.date(2023, 12, 31),
            ),
        ),
    )

    summary = reasoning_layer.draft_answer(
        dataclasses.replace(prepared_data, request=open_ended_request)
    ).summary

    assert "in the period through " in summary
    assert "in through" not in summary


def test_figure_free_result_shape_grouped_lists_all_seven_slot_names() -> None:
    slot_values = reasoning_layer.compute_slot_values(
        narrative_cases.prepared_revenue_by_region()
    )

    result_shape = reasoning_layer.figure_free_result_shape(slot_values)

    assert result_shape == {
        "available_slots": (
            "metric",
            "time_range",
            "metric_total",
            "dimension",
            "dimension_count",
            "top_dimension",
            "top_value",
        ),
    }


def test_figure_free_result_shape_scalar_lists_only_scalar_slot_names() -> None:
    slot_values = reasoning_layer.compute_slot_values(
        narrative_cases.prepared_customer_count()
    )

    result_shape = reasoning_layer.figure_free_result_shape(slot_values)

    assert result_shape == {
        "available_slots": ("metric", "time_range", "metric_total"),
    }


def test_figure_free_result_shape_carries_no_computed_value() -> None:
    slot_values = reasoning_layer.compute_slot_values(
        narrative_cases.prepared_revenue_by_region()
    )

    result_shape = reasoning_layer.figure_free_result_shape(slot_values)

    flat = repr(result_shape)
    for leaked in ("West", "2026", "$", "5,150", "1,600", "regions"):
        assert leaked not in flat
    # The bare scalar dimension_count value (1) must not leak for a scalar query.
    scalar_shape = reasoning_layer.figure_free_result_shape(
        reasoning_layer.compute_slot_values(narrative_cases.prepared_customer_count())
    )
    assert "1" not in repr(scalar_shape)


def test_grounding_passes_clean_slot_only_prose() -> None:
    proposal = reasoning_layer.NarrativeProposal(
        summary="{metric} in {time_range} led by {top_dimension}."
    )

    assert reasoning_layer.proposal_is_grounded(proposal) is True


def test_grounding_fails_prose_with_a_bare_digit() -> None:
    proposal = reasoning_layer.NarrativeProposal(summary="West led by 6%.")

    assert reasoning_layer.proposal_is_grounded(proposal) is False


def test_draft_narrative_fills_slots_and_matches_floor_numbers() -> None:
    prepared_data = narrative_cases.prepared_revenue_by_region()
    proposal = reasoning_layer.NarrativeProposal(
        summary=(
            "{metric} across {dimension_count} {dimension} totaled "
            "{metric_total} in {time_range}, with {top_dimension} on top at "
            "{top_value}."
        )
    )

    answer_draft = reasoning_layer.draft_narrative(
        prepared_data,
        provider=reasoning_support.fixed_narrative_provider(proposal),
    )
    deterministic = reasoning_layer.draft_answer(prepared_data)

    assert answer_draft.summary == (
        "Total revenue across 5 regions totaled $5,150.00 in January 2026, "
        "with West on top at $1,600.00."
    )
    # Numbers, caveats, datasets all match the deterministic floor.
    assert answer_draft.caveats == deterministic.caveats
    assert answer_draft.datasets_used == deterministic.datasets_used
    assert answer_draft.dataset_tables_used == deterministic.dataset_tables_used
    assert answer_draft.metric_kind == deterministic.metric_kind
    assert answer_draft.time_range == deterministic.time_range
    assert answer_draft.filters == deterministic.filters
    assert answer_draft.key_data is prepared_data.data


def test_draft_narrative_degrades_visibly_when_proposal_slips_a_digit() -> None:
    prepared_data = narrative_cases.prepared_revenue_by_region()
    proposal = reasoning_layer.NarrativeProposal(summary="West led by 6%.")

    answer_draft = reasoning_layer.draft_narrative(
        prepared_data,
        provider=reasoning_support.fixed_narrative_provider(proposal),
    )
    deterministic = reasoning_layer.draft_answer(prepared_data)

    assert answer_draft.summary == deterministic.summary
    assert answer_draft.caveats == (
        *deterministic.caveats,
        reasoning_layer.WITHHELD_WORDING_CAVEAT,
    )


def test_draft_narrative_degrades_when_proposal_repeats_metric_modifier() -> None:
    prepared_data = narrative_cases.prepared_customer_count()
    proposal = reasoning_layer.NarrativeProposal(
        summary="In {time_range}, the total {metric} reached {metric_total}."
    )

    answer_draft = reasoning_layer.draft_narrative(
        prepared_data,
        provider=reasoning_support.fixed_narrative_provider(proposal),
    )
    deterministic = reasoning_layer.draft_answer(prepared_data)

    assert answer_draft.summary == deterministic.summary
    assert "total Customer count" not in answer_draft.summary
    assert answer_draft.caveats == (
        *deterministic.caveats,
        reasoning_layer.WITHHELD_WORDING_CAVEAT,
    )


def test_draft_narrative_degrades_on_provider_failure() -> None:
    prepared_data = narrative_cases.prepared_revenue_by_region()

    answer_draft = reasoning_layer.draft_narrative(
        prepared_data,
        provider=reasoning_support.provider_failure_provider(),
    )
    deterministic = reasoning_layer.draft_answer(prepared_data)

    assert answer_draft.summary == deterministic.summary
    assert answer_draft.caveats == (
        *deterministic.caveats,
        reasoning_layer.WITHHELD_WORDING_CAVEAT,
    )


def test_draft_narrative_success_path_does_not_add_withheld_caveat() -> None:
    prepared_data = narrative_cases.prepared_revenue_by_region()
    proposal = reasoning_layer.NarrativeProposal(
        summary="{metric} in {time_range} was led by {top_dimension}."
    )

    answer_draft = reasoning_layer.draft_narrative(
        prepared_data,
        provider=reasoning_support.fixed_narrative_provider(proposal),
    )

    assert reasoning_layer.WITHHELD_WORDING_CAVEAT not in answer_draft.caveats


def test_fill_narrative_fills_a_slot_only_summary() -> None:
    proposal = reasoning_layer.NarrativeProposal(
        summary="{metric} in {time_range} led by {top_dimension}."
    )

    filled = reasoning_layer.fill_narrative(
        proposal,
        {
            "metric": "Total revenue",
            "time_range": "January 2026",
            "top_dimension": "West",
        },
    )

    assert filled == "Total revenue in January 2026 led by West."


def test_fill_narrative_returns_none_for_unknown_slot() -> None:
    proposal = reasoning_layer.NarrativeProposal(summary="{metric} led by {region}.")

    filled = reasoning_layer.fill_narrative(proposal, {"metric": "Total revenue"})

    assert filled is None


def test_fill_narrative_returns_none_for_malformed_brace() -> None:
    proposal = reasoning_layer.NarrativeProposal(summary="{metric} led by {top.")

    filled = reasoning_layer.fill_narrative(proposal, {"metric": "Total revenue"})

    assert filled is None


def test_draft_narrative_degrades_visibly_when_proposal_uses_unknown_slot() -> None:
    prepared_data = narrative_cases.prepared_revenue_by_region()
    proposal = reasoning_layer.NarrativeProposal(
        summary="{metric} in {time_range} led by {region}."
    )

    answer_draft = reasoning_layer.draft_narrative(
        prepared_data,
        provider=reasoning_support.fixed_narrative_provider(proposal),
    )
    deterministic = reasoning_layer.draft_answer(prepared_data)

    assert answer_draft.summary == deterministic.summary
    assert answer_draft.caveats == (
        *deterministic.caveats,
        reasoning_layer.WITHHELD_WORDING_CAVEAT,
    )


def test_narrative_proposal_forbids_extra_fields() -> None:
    try:
        reasoning_layer.NarrativeProposal(
            summary="{metric}.",
            caveat="model-authored",  # type: ignore[call-arg]
        )
    except pydantic.ValidationError:
        return
    raise AssertionError("NarrativeProposal should forbid extra fields")

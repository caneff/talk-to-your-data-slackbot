"""Behavior tests for grounded narration in the Reasoning Layer (ADR-0012)."""

import pydantic

import data_assistant.reasoning_layer as reasoning_layer
import data_assistant.reasoning_layer.narrative_cases as narrative_cases
import data_assistant.reasoning_layer.test_support as reasoning_support


def test_compute_slot_values_ranks_grouped_prepared_data() -> None:
    slot_values = reasoning_layer.compute_slot_values(
        narrative_cases.prepared_revenue_by_region()
    )

    assert slot_values == {
        "metric": "Total revenue",
        "time_range": "2026-01-01 through 2026-01-31",
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
        "time_range": "2026-01-01 through 2026-01-31",
        "metric_total": "1,234",
        "dimension": "",
        "dimension_count": 1,
        "top_dimension": "",
        "top_value": "",
    }


def test_figure_free_result_shape_withholds_values() -> None:
    slot_values = reasoning_layer.compute_slot_values(
        narrative_cases.prepared_revenue_by_region()
    )

    result_shape = reasoning_layer.figure_free_result_shape(slot_values)

    assert result_shape == {
        "metric": "Total revenue",
        "time_range": "2026-01-01 through 2026-01-31",
        "dimension": "regions",
        "dimension_count": 5,
        "top_dimension": "West",
    }


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
        "Total revenue across 5 regions totaled $5,150.00 in "
        "2026-01-01 through 2026-01-31, with West on top at $1,600.00."
    )
    # Numbers, caveats, freshness, datasets all match the deterministic floor.
    assert answer_draft.caveats == deterministic.caveats
    assert answer_draft.datasets_used == deterministic.datasets_used
    assert answer_draft.dataset_tables_used == deterministic.dataset_tables_used
    assert answer_draft.metric_kind == deterministic.metric_kind
    assert answer_draft.time_range == deterministic.time_range
    assert answer_draft.filters == deterministic.filters
    assert answer_draft.freshness == deterministic.freshness
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
            "time_range": "2026-01-01 through 2026-01-31",
            "top_dimension": "West",
        },
    )

    assert filled == "Total revenue in 2026-01-01 through 2026-01-31 led by West."


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

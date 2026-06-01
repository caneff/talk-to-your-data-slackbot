"""Behavior tests for grounded narration in the Reasoning Layer (ADR-0012)."""

import datetime

import pandas as pd
import pydantic

import data_assistant.reasoning_layer as reasoning_layer
import data_assistant.reasoning_layer.test_support as reasoning_support
import data_assistant.semantic_layer.schema as schema
import data_assistant.workflow.contracts as contracts


def _commerce_revenue_dataset() -> schema.CuratedDataset:
    return schema.CuratedDataset(
        dataset_id="commerce",
        name="Commerce",
        tables=("orders",),
        information_types=("revenue",),
        freshness=schema.Freshness(
            as_of=datetime.date(2026, 1, 31),
            description="Commerce order data refreshed through 2026-01-31.",
        ),
        example_questions=(),
    )


def _orders_table() -> schema.DatasetTable:
    return schema.DatasetTable(
        table_id="orders",
        dataset_id="commerce",
        description="Orders by date and region.",
        columns=(
            schema.TableColumn(column_id="order_date", data_type="date"),
            schema.TableColumn(column_id="region", data_type="varchar"),
            schema.TableColumn(column_id="revenue", data_type="decimal"),
        ),
        metrics=(
            schema.Metric(
                metric_id="total_revenue",
                label="total revenue",
                expression="sum(revenue)",
                source_column="revenue",
                kind=schema.MetricKind.MONEY,
            ),
        ),
        fields=(
            schema.SemanticField(
                field_id="region",
                label="region",
                source_column="region",
                data_type=schema.DataType.STRING,
                operations=(schema.FieldOperation.GROUP_BY,),
            ),
            schema.SemanticField(
                field_id="order_date",
                label="order date",
                source_column="order_date",
                data_type=schema.DataType.DATE,
                operations=(schema.FieldOperation.RANGE_FILTER,),
            ),
        ),
    )


def _prepared_revenue_by_region() -> contracts.PreparedData:
    dataset = _commerce_revenue_dataset()
    table = _orders_table()
    return contracts.PreparedData(
        request=contracts.DataRequest(
            dataset=dataset,
            table=table,
            metric=table.metrics[0],
            group_by_fields=(table.fields[0],),
            filter_operations=(
                contracts.ResolvedSemanticFieldOperation(
                    operation=schema.FieldOperation.RANGE_FILTER,
                    field=table.fields[1],
                    lower=datetime.date(2026, 1, 1),
                    upper=datetime.date(2026, 1, 31),
                ),
            ),
            output_shape="grouped_metric",
            result_limit=10,
        ),
        # Already ordered metric_value desc, dimension_value asc.
        data=pd.DataFrame(
            {
                "dimension_value": ("West", "North", "East", "South", "Unknown"),
                "metric_value": (1600.0, 1500.0, 950.0, 850.0, 250.0),
            }
        ),
        quality_notes=(
            "1 row excluded because revenue was missing.",
            "1 row grouped under Unknown because region was missing.",
        ),
    )


def _prepared_customer_count() -> contracts.PreparedData:
    dataset = schema.CuratedDataset(
        dataset_id="commerce",
        name="Commerce Customers",
        tables=("customers",),
        information_types=("customers",),
        freshness=schema.Freshness(
            as_of=datetime.date(2026, 1, 31),
            description="Commerce customer data refreshed through 2026-01-31.",
        ),
        example_questions=(),
    )
    table = schema.DatasetTable(
        table_id="customers",
        dataset_id="commerce",
        description="Customers by region.",
        columns=(
            schema.TableColumn(column_id="created_date", data_type="date"),
            schema.TableColumn(column_id="customer_id", data_type="string"),
        ),
        metrics=(
            schema.Metric(
                metric_id="customer_count",
                label="customer count",
                expression="count(customer_id)",
                source_column="customer_id",
                kind=schema.MetricKind.COUNT,
            ),
        ),
        fields=(
            schema.SemanticField(
                field_id="created_date",
                label="created date",
                source_column="created_date",
                data_type=schema.DataType.DATE,
                operations=(schema.FieldOperation.RANGE_FILTER,),
            ),
        ),
    )
    return contracts.PreparedData(
        request=contracts.DataRequest(
            dataset=dataset,
            table=table,
            metric=table.metrics[0],
            group_by_fields=(),
            filter_operations=(
                contracts.ResolvedSemanticFieldOperation(
                    operation=schema.FieldOperation.RANGE_FILTER,
                    field=table.fields[0],
                    lower=datetime.date(2026, 1, 1),
                    upper=datetime.date(2026, 1, 31),
                ),
            ),
            output_shape="scalar_metric",
            result_limit=1,
        ),
        data=pd.DataFrame({"metric_value": (1234,)}),
        quality_notes=(),
    )


def test_compute_slot_values_ranks_grouped_prepared_data() -> None:
    slot_values = reasoning_layer.compute_slot_values(_prepared_revenue_by_region())

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
    slot_values = reasoning_layer.compute_slot_values(_prepared_customer_count())

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
    slot_values = reasoning_layer.compute_slot_values(_prepared_revenue_by_region())

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
    prepared_data = _prepared_revenue_by_region()
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
    prepared_data = _prepared_revenue_by_region()
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
    prepared_data = _prepared_revenue_by_region()

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
    prepared_data = _prepared_revenue_by_region()
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
    prepared_data = _prepared_revenue_by_region()
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

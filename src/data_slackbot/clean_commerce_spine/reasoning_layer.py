"""Deterministic Reasoning Layer for clean commerce Prepared Data."""

from __future__ import annotations

import decimal

import data_slackbot.clean_commerce_spine.semantic_layer.loader as semantic_layer_loader
import data_slackbot.clean_commerce_spine.semantic_layer.schema as schema
import data_slackbot.clean_commerce_spine.workflow.contracts as contracts


def draft_answer(
    prepared_data: contracts.PreparedData,
    semantic_layer: schema.SemanticLayer,
) -> contracts.AnswerDraft:
    """Produce an Answer Draft from Prepared Data."""
    dataset = semantic_layer_loader.find_dataset(
        prepared_data.request.curated_dataset_id,
        semantic_layer,
    )
    total_revenue = sum(
        (row.total_revenue for row in prepared_data.rows),
        decimal.Decimal("0.00"),
    )
    summary = (
        f"Total revenue in {prepared_data.request.time_range.label} was "
        f"{_format_money(total_revenue)}, grouped across "
        f"{len(prepared_data.rows)} regions."
    )

    return contracts.AnswerDraft(
        summary=summary,
        key_numbers=prepared_data.rows,
        datasets_used=(dataset.name,),
        time_range=prepared_data.request.time_range.label,
        filters=prepared_data.request.filters,
        caveats=(dataset.freshness.description,),
    )


def _format_money(value: decimal.Decimal) -> str:
    return f"${value:,.2f}"

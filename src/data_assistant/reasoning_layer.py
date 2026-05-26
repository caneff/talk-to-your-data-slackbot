"""Deterministic Reasoning Layer for Data Assistant Prepared Data."""

from __future__ import annotations

import data_assistant.workflow.contracts as contracts


def draft_answer(
    prepared_data: contracts.PreparedData,
) -> contracts.AnswerDraft:
    """Produce an Answer Draft from Prepared Data."""
    dataset = prepared_data.request.dataset
    summary_values = {
        "metric": prepared_data.request.metric.label.capitalize(),
        "time_range": prepared_data.request.time_range.label,
        "metric_value": _format_money(float(prepared_data.data["metric_value"].sum())),
        "dimension_count": len(prepared_data.data),
        "dimension": _pluralize(prepared_data.request.dimension.label),
    }
    summary = (
        (
            "{metric} in {time_range} was {metric_value}, grouped across "
            "{dimension_count} {dimension}."
        )
        .strip()
        .replace("\n", " ")
        .format_map(summary_values)
    )

    return contracts.AnswerDraft(
        summary=summary,
        key_data=prepared_data.data,
        datasets_used=(dataset.name,),
        dataset_tables_used=(prepared_data.request.table.table_id,),
        time_range=prepared_data.request.time_range.label,
        filters=prepared_data.request.filters,
        freshness=dataset.freshness.description,
        caveats=prepared_data.quality_notes,
    )


def _format_money(value: float) -> str:
    return f"${value:,.2f}"


def _pluralize(label: str) -> str:
    if label.endswith("s"):
        return label
    return f"{label}s"

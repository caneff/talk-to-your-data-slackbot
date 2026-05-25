"""Deterministic Reasoning Layer for Data Assistant Prepared Data."""

from __future__ import annotations

import textwrap

import data_assistant.workflow.contracts as contracts


def draft_answer(
    prepared_data: contracts.PreparedData,
) -> contracts.AnswerDraft:
    """Produce an Answer Draft from Prepared Data."""
    dataset = prepared_data.request.dataset
    summary = textwrap.dedent(
        f"""
        {prepared_data.request.metric.label.capitalize()} in
        {prepared_data.request.time_range.label} was
        {_format_money(float(prepared_data.data["metric_value"].sum()))}, grouped across
        {len(prepared_data.data)} {_pluralize(prepared_data.request.dimension.label)}.
        """,
    ).strip().replace("\n", " ")

    return contracts.AnswerDraft(
        summary=summary,
        key_data=prepared_data.data,
        datasets_used=(dataset.name,),
        time_range=prepared_data.request.time_range.label,
        filters=prepared_data.request.filters,
        caveats=(dataset.freshness.description,),
    )


def _format_money(value: float) -> str:
    return f"${value:,.2f}"


def _pluralize(label: str) -> str:
    if label.endswith("s"):
        return label
    return f"{label}s"

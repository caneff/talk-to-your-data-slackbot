"""Deterministic Reasoning Layer for Data Assistant Prepared Data."""

from __future__ import annotations

import datetime

import data_assistant.semantic_layer.schema as schema
import data_assistant.workflow.contracts as contracts


def draft_answer(
    prepared_data: contracts.PreparedData,
) -> contracts.AnswerDraft:
    """Produce an Answer Draft from Prepared Data."""
    dataset = prepared_data.request.dataset
    group_by_fields = prepared_data.request.group_by_fields
    time_range = _time_range_label(prepared_data.request)
    summary_values = {
        "metric": prepared_data.request.metric.label.capitalize(),
        "time_range": time_range,
        "metric_value": _format_money(float(prepared_data.data["metric_value"].sum())),
        "dimension_count": len(prepared_data.data),
        "dimension": _pluralize(group_by_fields[0].label) if group_by_fields else "",
    }
    if group_by_fields:
        summary = (
            (
                "{metric} in {time_range} was {metric_value}, grouped across "
                "{dimension_count} {dimension}."
            )
            .strip()
            .replace("\n", " ")
            .format_map(summary_values)
        )
    else:
        summary = "{metric} in {time_range} was {metric_value}.".format_map(
            summary_values
        )

    return contracts.AnswerDraft(
        summary=summary,
        key_data=prepared_data.data,
        datasets_used=(dataset.name,),
        dataset_tables_used=(prepared_data.request.table.table_id,),
        time_range=time_range,
        filters=prepared_data.request.filter_labels,
        freshness=dataset.freshness.description,
        caveats=prepared_data.quality_notes,
    )


def _format_money(value: float) -> str:
    return f"${value:,.2f}"


def _pluralize(label: str) -> str:
    if label.endswith("s"):
        return label
    return f"{label}s"


def _time_range_label(data_request: contracts.DataRequest) -> str:
    for operation in data_request.filter_operations:
        if operation.field.data_type != "date":
            continue
        if operation.operation == schema.FieldOperation.RANGE_FILTER:
            lower = _format_date_bound(operation.lower)
            upper = _format_date_bound(operation.upper)
            if lower is not None and upper is not None:
                return f"{lower} through {upper}"
            if lower is not None:
                return f"from {lower}"
            if upper is not None:
                return f"through {upper}"
        if operation.operation == schema.FieldOperation.INCLUDE_FILTER:
            return ", ".join(str(value) for value in operation.values)
    return "all available data"


def _format_date_bound(value: contracts.FieldValue | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime.date):
        return value.isoformat()
    return str(value)

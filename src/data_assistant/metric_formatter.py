"""Render metric values from Semantic Layer presentation kind."""

from __future__ import annotations

import data_assistant.semantic_layer.schema as schema


def format_metric_value(value: float, kind: schema.MetricKind) -> str:
    """Render a metric value for user-facing answer text."""
    if kind == schema.MetricKind.MONEY:
        return f"${value:,.2f}"
    return f"{value:,.0f}"

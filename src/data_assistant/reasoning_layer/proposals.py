"""Reasoning Layer slot computation and untrusted provider contracts."""

from __future__ import annotations

import dataclasses
import datetime
import typing

import pydantic

import data_assistant.metric_formatter as metric_formatter
import data_assistant.semantic_layer.schema as schema
import data_assistant.workflow.contracts as contracts

# Fixed, closed set of Narrative Slots the Reasoning Layer fills
# deterministically (see ADR-0012). Slot names never contain digits.
SLOT_NAMES: tuple[str, ...] = (
    "metric",
    "time_range",
    "metric_total",
    "dimension",
    "dimension_count",
    "top_dimension",
    "top_value",
)

# The figure-free subset handed to the provider as result_shape: labels and
# ranking by name only, with every value-bearing slot withheld.
_FIGURE_BEARING_SLOTS: frozenset[str] = frozenset({"metric_total", "top_value"})


class NarrativeProposal(pydantic.BaseModel):
    """Untrusted provider proposal for narrative prose around Narrative Slots."""

    model_config = pydantic.ConfigDict(extra="forbid")

    summary: str = pydantic.Field(
        description=(
            "Narrative prose written around the fixed Narrative Slots "
            "(for example {metric}, {time_range}, {dimension}). Never write a "
            "literal figure or any digit; reference quantities only through "
            "slots."
        ),
    )


@dataclasses.dataclass(frozen=True)
class ProviderFailure:
    """Reasoning provider failed to produce a proposal."""

    reason: str


class ReasoningProvider(typing.Protocol):
    """Provider boundary for narrative proposals."""

    def propose_narrative(
        self,
        *,
        result_shape: dict[str, object],
    ) -> NarrativeProposal | ProviderFailure:
        """Return an untrusted narrative proposal or failure."""
        ...


def compute_slot_values(
    prepared_data: contracts.PreparedData,
) -> dict[str, object]:
    """Compute the full set of Narrative Slot values from Prepared Data.

    Single source of truth feeding the figure-free ``result_shape``, the
    LLM slot-fill, and the deterministic floor.
    """
    request = prepared_data.request
    group_by_fields = request.group_by_fields
    data = prepared_data.data

    metric_total = metric_formatter.format_metric_value(
        float(data["metric_value"].sum()),
        request.metric.kind,
    )

    if group_by_fields:
        dimension = _pluralize(group_by_fields[0].label)
        top_dimension = str(data["dimension_value"].iloc[0])
        top_value = metric_formatter.format_metric_value(
            float(data["metric_value"].iloc[0]),
            request.metric.kind,
        )
    else:
        dimension = ""
        top_dimension = ""
        top_value = ""

    return {
        "metric": request.metric.label.capitalize(),
        "time_range": _time_range_label(request),
        "metric_total": metric_total,
        "dimension": dimension,
        "dimension_count": len(data),
        "top_dimension": top_dimension,
        "top_value": top_value,
    }


def figure_free_result_shape(slot_values: dict[str, object]) -> dict[str, object]:
    """Return the value-withheld subset of slots handed to the provider."""
    return {
        name: value
        for name, value in slot_values.items()
        if name not in _FIGURE_BEARING_SLOTS
    }


def fill_narrative(
    proposal: NarrativeProposal,
    slot_values: dict[str, object],
) -> str | None:
    """Fill slots; None if prose references an unknown slot or malformed brace."""
    try:
        return proposal.summary.format_map(slot_values)
    except (KeyError, ValueError, IndexError):
        return None


def proposal_is_grounded(proposal: NarrativeProposal) -> bool:
    """Return whether the raw proposal prose contains no ungrounded digit.

    Inspected before slot substitution. Any digit anywhere in the prose is a
    violation; slot names contain no digits, so unfilled slots are fine.
    """
    return not any(ch.isdigit() for ch in proposal.summary)


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

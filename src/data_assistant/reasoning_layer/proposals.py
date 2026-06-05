"""Reasoning Layer slot computation and untrusted provider contracts."""

from __future__ import annotations

import calendar
import dataclasses
import datetime
import typing

import pydantic

import data_assistant.metric_formatter as metric_formatter
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

# The slot tokens available for a scalar (no group-by) query, in SLOT_NAMES
# order. A grouped query additionally exposes the four grouping slots.
_SCALAR_SLOT_NAMES: tuple[str, ...] = ("metric", "time_range", "metric_total")
_GROUPING_SLOT_NAMES: tuple[str, ...] = (
    "dimension",
    "dimension_count",
    "top_dimension",
    "top_value",
)
_REDUNDANT_METRIC_MODIFIERS = frozenset({"total", "sum", "count"})


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
    group_by_field = request.group_by_field
    data = prepared_data.data

    metric_total = metric_formatter.format_metric_value(
        float(data["metric_value"].sum()),
        request.metric.kind,
    )

    if group_by_field is not None:
        dimension = _pluralize(group_by_field.label)
        if data.empty:
            top_dimension = ""
            top_value = ""
        else:
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
    """Return the fully value-free Result Shape handed to the provider.

    Carries only ``available_slots`` — the slot-token names writeable for this
    query, in :data:`SLOT_NAMES` order — and never any slot contents (see
    ADR-0012). Grouped-vs-scalar is derived from whether the ``dimension`` slot
    is populated, not from value truthiness: a scalar query's
    ``dimension_count`` is ``1`` (truthy) yet must not leak.
    """
    is_grouped = bool(slot_values.get("dimension"))
    available_slots = _SCALAR_SLOT_NAMES + (_GROUPING_SLOT_NAMES if is_grouped else ())
    return {"available_slots": available_slots}


def fill_narrative(
    proposal: NarrativeProposal,
    slot_values: dict[str, object],
) -> str | None:
    """Fill slots; None if prose references an unknown slot or malformed brace."""
    if _has_redundant_metric_modifier(proposal.summary):
        return None
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


def _has_redundant_metric_modifier(summary: str) -> bool:
    words = summary.lower().replace("{metric}", " {metric} ").split()
    return any(
        word == "{metric}"
        and index > 0
        and words[index - 1].strip(",.;:") in _REDUNDANT_METRIC_MODIFIERS
        for index, word in enumerate(words)
    )


def _pluralize(label: str) -> str:
    if label.endswith("s"):
        return label
    return f"{label}s"


def _time_range_label(data_request: contracts.DataRequest) -> str:
    for field_filter in data_request.field_filters:
        if field_filter.field.data_type != "date":
            continue
        if isinstance(field_filter, contracts.RangeFilter):
            lower_date = (
                field_filter.lower
                if isinstance(field_filter.lower, datetime.date)
                else None
            )
            upper_date = (
                field_filter.upper
                if isinstance(field_filter.upper, datetime.date)
                else None
            )
            period_label = _friendly_period_label(lower_date, upper_date)
            if period_label is not None:
                return period_label
            lower = _format_date_bound(field_filter.lower)
            upper = _format_date_bound(field_filter.upper)
            if lower is not None and upper is not None:
                return f"{lower} through {upper}"
            if lower is not None:
                return f"the period from {lower}"
            if upper is not None:
                return f"the period through {upper}"
        if (
            isinstance(field_filter, contracts.ValuesFilter)
            and field_filter.mode == contracts.FilterMode.INCLUDE
        ):
            return ", ".join(str(value) for value in field_filter.values)
    return "all available data"


def _format_date_bound(value: contracts.FieldValue | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime.date):
        return _format_short_date(value)
    return str(value)


def _friendly_period_label(
    lower: datetime.date | None,
    upper: datetime.date | None,
) -> str | None:
    if lower is None and upper is None:
        return None
    if lower is not None and upper is not None:
        if lower == datetime.date(lower.year, 1, 1) and upper == datetime.date(
            lower.year, 12, 31
        ):
            return str(lower.year)
        if lower.year == upper.year:
            quarter = _calendar_quarter(lower, upper)
            if quarter is not None:
                return f"Q{quarter} {lower.year}"
            if _is_full_month(lower, upper):
                return lower.strftime("%B %Y")
            return _format_closed_date_range(lower, upper)
        return _format_closed_date_range(lower, upper)
    return None


def _calendar_quarter(lower: datetime.date, upper: datetime.date) -> int | None:
    quarter = ((lower.month - 1) // 3) + 1
    start_month = (quarter - 1) * 3 + 1
    if lower != datetime.date(lower.year, start_month, 1):
        return None
    end_month = start_month + 2
    end_day = calendar.monthrange(upper.year, end_month)[1]
    if upper != datetime.date(upper.year, end_month, end_day):
        return None
    return quarter


def _is_full_month(lower: datetime.date, upper: datetime.date) -> bool:
    return (
        lower.year == upper.year
        and lower.month == upper.month
        and lower.day == 1
        and upper.day == calendar.monthrange(upper.year, upper.month)[1]
    )


def _format_closed_date_range(lower: datetime.date, upper: datetime.date) -> str:
    if lower.year == upper.year:
        return (
            f"{lower.strftime('%b')} {lower.day} - "
            f"{upper.strftime('%b')} {upper.day}, {upper.year}"
        )
    return (
        f"{lower.strftime('%b')} {lower.day}, {lower.year} - "
        f"{upper.strftime('%b')} {upper.day}, {upper.year}"
    )


def _format_short_date(value: datetime.date) -> str:
    return value.strftime("%b") + f" {value.day}, {value.year}"

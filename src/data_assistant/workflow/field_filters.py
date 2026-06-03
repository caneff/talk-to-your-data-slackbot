"""Shared filter contracts across trusted workflow stages."""

from __future__ import annotations

import dataclasses
import datetime
import decimal
import enum
import typing

FieldRefT = typing.TypeVar("FieldRefT")

# Filter values are validated and typed at the Question Interpreter trust
# boundary (see docs/adr/0008); downstream stages consume typed values and
# never re-parse strings.
FieldValue: typing.TypeAlias = datetime.date | decimal.Decimal | str


class FilterMode(enum.StrEnum):
    INCLUDE = "include"
    EXCLUDE = "exclude"


@dataclasses.dataclass(frozen=True)
class RangeFilter(typing.Generic[FieldRefT]):
    field: FieldRefT
    lower: FieldValue | None = None
    upper: FieldValue | None = None


@dataclasses.dataclass(frozen=True)
class ValuesFilter(typing.Generic[FieldRefT]):
    field: FieldRefT
    mode: FilterMode
    values: tuple[FieldValue, ...]


FieldFilter: typing.TypeAlias = RangeFilter[FieldRefT] | ValuesFilter[FieldRefT]


def render_filter_label(
    field_filter: FieldFilter[FieldRefT],
    *,
    field_label: str | None = None,
) -> str:
    label = field_label or _field_label(field_filter.field)
    if isinstance(field_filter, RangeFilter):
        bounds: list[str] = []
        if field_filter.lower is not None:
            bounds.append(f">= {_format_field_value(field_filter.lower)}")
        if field_filter.upper is not None:
            bounds.append(f"<= {_format_field_value(field_filter.upper)}")
        return f"{label} {' and '.join(bounds)}"
    values = ", ".join(_format_field_value(value) for value in field_filter.values)
    verb = "in" if field_filter.mode == FilterMode.INCLUDE else "not in"
    return f"{label} {verb} ({values})"


def _field_label(field: object) -> str:
    if isinstance(field, str):
        return field
    label = getattr(field, "label", None)
    if isinstance(label, str):
        return label
    raise TypeError("field_label is required for filters without a label attribute")


def _format_field_value(value: FieldValue) -> str:
    if isinstance(value, datetime.date):
        return value.isoformat()
    return str(value)

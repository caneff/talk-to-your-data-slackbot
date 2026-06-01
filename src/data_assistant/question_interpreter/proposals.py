"""Untrusted Question Interpreter provider proposal contracts."""

from __future__ import annotations

import dataclasses
import typing

import pydantic


class FieldOperationProposal(pydantic.BaseModel):
    """Untrusted provider proposal for one Semantic Field operation."""

    model_config = pydantic.ConfigDict(extra="forbid")

    operation: typing.Literal[
        "group_by",
        "range_filter",
        "include_filter",
        "exclude_filter",
    ] = pydantic.Field(
        description=(
            "Use group_by for requested grouping, range_filter for complete "
            "calendar months or date ranges, include_filter for exact dates or "
            "explicitly included dimension values, and exclude_filter only for "
            "explicitly excluded values with non-empty values. Do not emit "
            "operations for fields that are merely available in "
            "semantic_layer_context, and never use include_filter or "
            "exclude_filter with empty values."
        ),
    )
    field: str = pydantic.Field(
        description="Business-facing Semantic Field label from semantic_layer_context.",
    )
    lower: str | None = pydantic.Field(
        default=None,
        description=(
            "Lower range_filter value. Use ISO YYYY-MM-DD for date ranges. "
            "Null for group_by, include_filter, and exclude_filter. At least "
            "one of lower or upper must be non-null for range_filter."
        ),
    )
    upper: str | None = pydantic.Field(
        default=None,
        description=(
            "Upper range_filter value. Use ISO YYYY-MM-DD for date ranges. "
            "Null for group_by, include_filter, and exclude_filter. At least "
            "one of lower or upper must be non-null for range_filter."
        ),
    )
    values: tuple[str, ...] = pydantic.Field(
        default=(),
        description=(
            "Non-empty explicit date or dimension values for include_filter or "
            "exclude_filter. Empty only for group_by and range_filter; never "
            "emit include_filter or exclude_filter with empty values."
        ),
    )


GroupByOperationProposal = FieldOperationProposal
RangeFilterOperationProposal = FieldOperationProposal
IncludeFilterOperationProposal = FieldOperationProposal
ExcludeFilterOperationProposal = FieldOperationProposal


class QuestionFrameProposal(pydantic.BaseModel):
    """Untrusted provider proposal shape for a Question Frame."""

    model_config = pydantic.ConfigDict(extra="forbid")

    intent: str | None = pydantic.Field(
        description=(
            "Use summarize for supported Data Questions that ask for historical "
            "metric totals, summaries, or grouped results, including phrases "
            "like 'what was', 'show', and 'summarize'. Use rank for deferred "
            "top/bottom questions that ask for highest, lowest, most, least, "
            "biggest, smallest, top, or bottom results. Other deferred intent "
            "names such as compare, trend, forecast, explain, prescribe, or "
            "diagnose are allowed for clearly classified unsupported Data "
            "Questions. Use null only when no Data Question intent applies."
        ),
    )
    metric: str | None = pydantic.Field(
        description=(
            "Business-facing Semantic Metric label from semantic_layer_context, "
            "or null when no matching metric is present. Unsupported intents "
            "still set this when the Data Question names a known metric."
        ),
    )
    field_operations: tuple[FieldOperationProposal, ...] = pydantic.Field(
        description=(
            "Every explicit grouping, date constraint, and filter from the "
            "Data Question, represented with Semantic Field labels. Do not add "
            "operations for fields that are merely available in context or "
            "examples. If the question omits time, omit date operations."
        ),
    )
    all_time: bool = pydantic.Field(
        default=False,
        description=(
            "True only when the Data Question explicitly asks across all time "
            "and no date filter operation is emitted."
        ),
    )


@dataclasses.dataclass(frozen=True)
class ProviderFailure:
    """Provider failed to produce a proposal."""

    reason: str


class QuestionInterpreterProvider(typing.Protocol):
    """Provider boundary for Question Frame proposals."""

    def propose_question_frame(
        self,
        *,
        question: str,
        semantic_layer_context: dict[str, object],
    ) -> QuestionFrameProposal | ProviderFailure:
        """Return an untrusted Question Frame proposal or failure."""
        ...

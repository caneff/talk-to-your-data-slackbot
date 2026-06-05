"""Untrusted Question Interpreter provider proposal contracts."""

from __future__ import annotations

import dataclasses
import enum
import typing

import pydantic


class ProviderFieldOperation(pydantic.BaseModel):
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


class ProviderRelativeWindow(pydantic.BaseModel):
    """Untrusted model classification of an as_of-anchored relative phrase.

    The model classifies ONLY; the interpreter computes the calendar window
    from as_of_date (ADR-0025). No dates appear here.
    """

    model_config = pydantic.ConfigDict(extra="forbid")

    field: str = pydantic.Field(
        description=(
            "Business-facing date Semantic Field label from "
            "semantic_layer_context — the selected metric's own compatible date "
            "field, exactly as for an explicit range_filter."
        ),
    )
    unit: typing.Literal["day", "month", "quarter"] = pydantic.Field(
        description=(
            "The relative phrase's unit: day for yesterday/last N days, month "
            "for last month/last M months, quarter for last quarter/last M "
            "quarters."
        ),
    )
    count: int = pydantic.Field(
        ge=1,
        description=(
            "How many units back the phrase names: 1 for yesterday/last "
            "month/last quarter, N for last N days, M for last M months/quarters."
        ),
    )


class ProviderProposal(pydantic.BaseModel):
    """Untrusted provider proposal shape for a Question Frame."""

    model_config = pydantic.ConfigDict(extra="forbid")

    intent: str | None = pydantic.Field(
        description=(
            "Use summarize for supported Data Questions that ask for historical "
            "metric totals, summaries, or grouped results, including phrases "
            "like 'what was', 'show', and 'summarize'. Use rank for supported "
            "top/bottom questions that ask for highest, lowest, most, least, "
            "biggest, smallest, top, or bottom results. Use "
            "catalog_discovery for supported metadata requests about what kinds "
            "of data the caller can query, such as 'What sorts of data can I "
            "query?'. Other deferred intent names such as compare, trend, "
            "forecast, explain, prescribe, or diagnose are allowed for clearly "
            "classified unsupported Data Questions. Use null only when no Data "
            "Question intent applies."
        ),
    )
    metric: str | None = pydantic.Field(
        description=(
            "Business-facing Semantic Metric label from semantic_layer_context, "
            "or null when no matching metric is present. Unsupported intents "
            "still set this when the Data Question names a known metric."
        ),
    )
    metric_ambiguity: str | None = pydantic.Field(
        default=None,
        description=(
            "Set to the verbatim ambiguous metric wording from the Data Question "
            "when its metric carries a qualifier (e.g. net, gross, recurring, "
            "organic) that no available metric label reflects, such that matching "
            "a label would drop or alter a word that changes which measure is "
            "computed. When set, leave metric null, leave unknown_metric null, "
            "and do not guess a label. Never set metric_ambiguity together with "
            "unknown_metric, and never copy the same wording into both fields. "
            "Use this only for qualifier-drop cases on otherwise available "
            "metric labels, not for full derived metric names such as average "
            "order value (AOV), conversion rate, return rate, or other "
            "rate/ratio/percentage/value-per formulas. Leave null when the "
            "metric is unambiguous or genuinely synonymous with an available "
            "label."
        ),
    )
    unknown_metric: str | None = pydantic.Field(
        default=None,
        description=(
            "Set to the verbatim metric wording from the Data Question when it "
            "clearly names a metric and no available metric label actually names "
            "or computes that measure, even if nearby base measures or related "
            "counts exist. When set, leave metric null, leave "
            "metric_ambiguity null, and do not guess a label. Never set "
            "unknown_metric together with metric_ambiguity. Leave null when an "
            "available label matches or when the wording is merely a "
            "metric-qualifier ambiguity (use metric_ambiguity instead). "
            "Unavailable derived formulas such as AOV, rates, ratios, "
            "percentages, or value-per measures belong here, not in "
            "metric_ambiguity."
        ),
    )
    field_operations: tuple[ProviderFieldOperation, ...] = pydantic.Field(
        description=(
            "Every explicit grouping, date constraint, and filter from the "
            "Data Question, represented with Semantic Field labels. Do not add "
            "operations for fields that are merely available in context or "
            "examples. If the question omits time, omit date operations."
        ),
    )
    limit: int | None = pydantic.Field(
        default=None,
        description=(
            "Explicit top-N or bottom-N count for intent rank. Use null when "
            "the question does not name a count; downstream defaults the rank "
            "limit to the standard bounded result limit."
        ),
    )
    sort_direction: typing.Literal["asc", "desc"] | None = pydantic.Field(
        default=None,
        description=(
            "For intent rank, use desc for top, highest, most, biggest, or "
            "first-ranked asks; use asc for bottom, lowest, least, smallest, "
            "or last-ranked asks. Null for non-rank intents."
        ),
    )
    all_time: bool = pydantic.Field(
        default=False,
        description=(
            "True only when the Data Question explicitly asks across all time "
            "and no date filter operation is emitted."
        ),
    )
    relative_window: ProviderRelativeWindow | None = pydantic.Field(
        default=None,
        description=(
            "Classify ONLY an as_of-anchored relative phrase (yesterday, last N "
            "days, last month, last M months, last quarter, last M quarters) "
            "into the selected date field plus unit and count; emit NO "
            "range_filter and NO dates for it, because the interpreter computes "
            "the window from as_of_date. Mutually exclusive with a date "
            "range_filter: a proposal carries one or the other, never both. "
            "Null for explicit dates, explicit months/quarters, bare months, "
            "and 'before <month>' phrases, which stay model-emitted range_filter."
        ),
    )


class ProviderFailureDiagnosticClass(enum.StrEnum):
    """Safe maintainer-facing classes for provider failure diagnosis."""

    PROVIDER_EXCEPTION = "provider_exception"
    PROVIDER_REFUSAL = "provider_refusal"
    MISSING_PARSED_OUTPUT = "missing_parsed_output"
    STRUCTURED_OUTPUT_RETRY_EXHAUSTED = "structured_output_retry_exhausted"


@dataclasses.dataclass(frozen=True)
class ProviderFailure:
    """Provider failed to produce a proposal."""

    reason: str
    diagnostic_class: ProviderFailureDiagnosticClass | None = None


class QuestionInterpreterProvider(typing.Protocol):
    """Provider boundary for Provider Proposals."""

    def propose_question_frame(
        self,
        *,
        question: str,
        semantic_layer_context: dict[str, object],
    ) -> ProviderProposal | ProviderFailure:
        """Return an untrusted Provider Proposal or failure."""
        ...

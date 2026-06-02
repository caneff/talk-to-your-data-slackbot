"""Pipeline handoff contracts for the Data Assistant."""

from __future__ import annotations

import dataclasses
import datetime
import decimal
import enum
import typing

import pandas as pd

import data_assistant.semantic_layer.schema as schema

T = typing.TypeVar("T")


# Filter values are validated and typed at the Question Interpreter trust
# boundary (see docs/adr/0008); downstream stages consume typed values and
# never re-parse strings.
FieldValue: typing.TypeAlias = datetime.date | decimal.Decimal | str


@dataclasses.dataclass(frozen=True)
class SemanticFieldOperation:
    """Validated provider-requested operation using Semantic Field labels."""

    operation: schema.FieldOperation
    field: str
    lower: FieldValue | None = None
    upper: FieldValue | None = None
    values: tuple[FieldValue, ...] = ()

    def filter_label(self) -> str | None:
        """Return user-facing filter summary when this operation filters rows."""
        if self.operation == schema.FieldOperation.GROUP_BY:
            return None
        if self.operation == schema.FieldOperation.RANGE_FILTER:
            bounds: list[str] = []
            if self.lower is not None:
                bounds.append(f">= {_format_field_value(self.lower)}")
            if self.upper is not None:
                bounds.append(f"<= {_format_field_value(self.upper)}")
            return f"{self.field} {' and '.join(bounds)}"
        values = ", ".join(_format_field_value(value) for value in self.values)
        verb = (
            "in" if self.operation == schema.FieldOperation.INCLUDE_FILTER else "not in"
        )
        return f"{self.field} {verb} ({values})"


@dataclasses.dataclass(frozen=True)
class ResolvedSemanticFieldOperation:
    """Validated Semantic Field operation resolved to Semantic Layer config."""

    operation: schema.FieldOperation
    field: schema.SemanticField
    lower: FieldValue | None = None
    upper: FieldValue | None = None
    values: tuple[FieldValue, ...] = ()

    def as_question_operation(self) -> SemanticFieldOperation:
        """Return business-facing operation without retrieval details."""
        return SemanticFieldOperation(
            operation=self.operation,
            field=self.field.label,
            lower=self.lower,
            upper=self.upper,
            values=self.values,
        )

    def filter_label(self) -> str | None:
        """Return user-facing filter summary when this operation filters rows."""
        return self.as_question_operation().filter_label()


def _format_field_value(value: FieldValue) -> str:
    if isinstance(value, datetime.date):
        return value.isoformat()
    return str(value)


class NonAnswerStage(enum.StrEnum):
    """Pipeline stage that returned a Non-Answer."""

    ACCESS_CONTROLLER = "access_controller"
    QUESTION_INTERPRETER = "question_interpreter"
    SEMANTIC_ROUTER = "semantic_router"


class TimeScope(enum.StrEnum):
    """Resolved temporal scope for a trusted Data Question."""

    BOUNDED = "bounded"
    ALL_TIME = "all_time"


@dataclasses.dataclass(frozen=True)
class QuestionFrame:
    """Structured interpretation of a Data Question."""

    intent: str
    metric: str
    time_scope: TimeScope
    field_operations: tuple[SemanticFieldOperation, ...]
    unresolved_ambiguities: tuple[str, ...]

    @property
    def filter_labels(self) -> tuple[str, ...]:
        """Return user-facing labels for field operations that filter rows."""
        return tuple(
            label
            for operation in self.field_operations
            if (label := operation.filter_label()) is not None
        )


@dataclasses.dataclass(frozen=True)
class InternalIdentity:
    """Internal caller identity passed into the workflow."""

    identity_id: str


@dataclasses.dataclass(frozen=True)
class Success(typing.Generic[T]):
    """Successful stage result."""

    value: T


class NonAnswerReasonCode(enum.StrEnum):
    """Typed reason categories for Non-Answer Responses."""

    # Caller lacks access to the selected Curated Dataset.
    ACCESS_DENIED = "access_denied"
    # More than one Curated Dataset matches or was selected.
    AMBIGUOUS_DATASET = "ambiguous_dataset"
    # Metric wording carries a qualifier ambiguous against available metrics.
    AMBIGUOUS_METRIC = "ambiguous_metric"
    # More than one Dataset Table can satisfy the Data Request.
    AMBIGUOUS_TABLE = "ambiguous_table"
    # Provider returned output that violates the required schema.
    INVALID_PROVIDER_OUTPUT = "invalid_provider_output"
    # Question Frame is missing a required business interpretation field.
    MISSING_REQUIRED_FIELD = "missing_required_field"
    # Question omits required time scope and must be clarified.
    MISSING_TIME_SCOPE = "missing_time_scope"
    # No Curated Dataset can answer the Question Frame.
    NO_MATCHING_DATASET = "no_matching_dataset"
    # No Dataset Table can satisfy the Question Frame.
    NO_MATCHING_TABLE = "no_matching_table"
    # Provider failed before returning usable output.
    PROVIDER_FAILURE = "provider_failure"
    # Provider proposed a label outside the Semantic Layer.
    UNKNOWN_SEMANTIC_LABEL = "unknown_semantic_label"
    # Question asks which data or periods exist rather than for a metric.
    UNSUPPORTED_AVAILABILITY = "unsupported_availability"
    # Question asks about data outside approved Curated Datasets.
    UNSUPPORTED_DATA = "unsupported_data"
    # Question uses filters not supported by the current workflow.
    UNSUPPORTED_FILTER = "unsupported_filter"
    # Question asks for a Semantic Field operation outside approved uses.
    UNSUPPORTED_FIELD_OPERATION = "unsupported_field_operation"
    # Question uses an intent not supported by the current workflow.
    UNSUPPORTED_INTENT = "unsupported_intent"
    # Question shape cannot be handled by the current interpreter.
    UNSUPPORTED_SHAPE = "unsupported_shape"


class ResponseKind(enum.StrEnum):
    """User-facing final response classification."""

    ACCESS_DENIAL = "access_denial"
    ANSWER = "answer"
    CLARIFICATION_NEEDED = "clarification_needed"
    UNSUPPORTED = "unsupported"


SlackBlock: typing.TypeAlias = dict[str, object]
ProgressSink: typing.TypeAlias = typing.Callable[[str], None]


@dataclasses.dataclass(frozen=True)
class NonAnswer:
    """Workflow short-circuit when a stage cannot safely proceed.

    Carries only structured classification; team-member-facing ``reason`` and
    ``next_step`` copy is rendered on demand from the Non-Answer Catalog (see
    ADR-0007).
    """

    stage: NonAnswerStage
    reason_code: NonAnswerReasonCode
    context: tuple[str, ...] = ()
    datasets: tuple[str, ...] = ()


StageResult: typing.TypeAlias = Success[T] | NonAnswer


@dataclasses.dataclass(frozen=True)
class DatasetSelection:
    """Semantic Router result for a Question Frame."""

    selected_datasets: tuple[schema.CuratedDataset, ...]
    match_rationale: str


@dataclasses.dataclass(frozen=True)
class SemanticMatch:
    """Resolved Semantic Layer objects that match a Question Frame."""

    dataset: schema.CuratedDataset
    table: schema.DatasetTable
    metric: schema.Metric
    group_by_fields: tuple[schema.SemanticField, ...]


@dataclasses.dataclass(frozen=True)
class AvailableDataResolution:
    """Trace of resolving Available Data to one canonical Semantic Match."""

    resolved_match: SemanticMatch
    dataset_selection: DatasetSelection


@dataclasses.dataclass(frozen=True)
class DataRequest:
    """Constrained request for bounded Prepared Data."""

    dataset: schema.CuratedDataset
    table: schema.DatasetTable
    metric: schema.Metric
    group_by_fields: tuple[schema.SemanticField, ...]
    filter_operations: tuple[ResolvedSemanticFieldOperation, ...]
    output_shape: str
    result_limit: int

    @property
    def filter_labels(self) -> tuple[str, ...]:
        """Return user-facing labels for row filters."""
        return tuple(
            label
            for operation in self.filter_operations
            if (label := operation.filter_label()) is not None
        )


@dataclasses.dataclass(frozen=True)
class PreparedData:
    """Bounded result produced from a Data Request."""

    request: DataRequest
    data: pd.DataFrame
    quality_notes: tuple[str, ...]


@dataclasses.dataclass(frozen=True)
class AnswerDraft:
    """Reasoning Layer answer proposal based on Prepared Data."""

    summary: str
    key_data: pd.DataFrame
    datasets_used: tuple[str, ...]
    dataset_tables_used: tuple[str, ...]
    metric_kind: schema.MetricKind
    metric_label: str
    time_range: str
    filters: tuple[str, ...]
    freshness: str
    caveats: tuple[str, ...]
    limitations: tuple[str, ...] = ()
    group_by_label: str | None = None


@dataclasses.dataclass(frozen=True)
class TrustSummary:
    """Structured trust summary for answer and non-answer responses."""

    datasets: tuple[str, ...] = ()
    dataset_tables: tuple[str, ...] = ()
    time_range: str | None = None
    filters: tuple[str, ...] = ()
    freshness: str | None = None
    caveats: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()


@dataclasses.dataclass(frozen=True)
class FinalResponse:
    """Final Response prepared by the Response Composer."""

    text: str
    trust_summary: TrustSummary
    response_kind: ResponseKind
    blocks: tuple[SlackBlock, ...] = ()
    # Set on the Non-Answer path so the Interaction Log (ADR-0016) records the
    # FINE 15-way reason_code + stage instead of the coarse 4-bucket
    # response_kind. The answer path leaves this None. Last field: backward
    # compatible with every existing constructor.
    non_answer: NonAnswer | None = None


@dataclasses.dataclass(frozen=True)
class DataAssistantRun:
    """Trace of a successful Data Assistant run."""

    question_frame: QuestionFrame
    available_data_resolution: AvailableDataResolution
    data_request: DataRequest
    prepared_data: PreparedData
    answer_draft: AnswerDraft
    final_response: FinalResponse


WorkflowResult: typing.TypeAlias = DataAssistantRun | FinalResponse

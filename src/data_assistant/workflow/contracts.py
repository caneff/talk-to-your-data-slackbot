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


class FieldOperationKind(enum.StrEnum):
    """Approved operation over a business-facing Semantic Field."""

    EXCLUDE_FILTER = "exclude_filter"
    GROUP_BY = "group_by"
    INCLUDE_FILTER = "include_filter"
    RANGE_FILTER = "range_filter"


FieldValue: typing.TypeAlias = datetime.date | decimal.Decimal | str


@dataclasses.dataclass(frozen=True)
class SemanticFieldOperation:
    """Validated provider-requested operation using Semantic Field labels."""

    operation: FieldOperationKind
    field: str
    lower: FieldValue | None = None
    upper: FieldValue | None = None
    values: tuple[FieldValue, ...] = ()

    def filter_label(self) -> str | None:
        """Return user-facing filter summary when this operation filters rows."""
        if self.operation == FieldOperationKind.GROUP_BY:
            return None
        if self.operation == FieldOperationKind.RANGE_FILTER:
            bounds: list[str] = []
            if self.lower is not None:
                bounds.append(f">= {_format_field_value(self.lower)}")
            if self.upper is not None:
                bounds.append(f"<= {_format_field_value(self.upper)}")
            return f"{self.field} {' and '.join(bounds)}"
        values = ", ".join(_format_field_value(value) for value in self.values)
        verb = "in" if self.operation == FieldOperationKind.INCLUDE_FILTER else "not in"
        return f"{self.field} {verb} ({values})"


@dataclasses.dataclass(frozen=True)
class ResolvedSemanticFieldOperation:
    """Validated Semantic Field operation resolved to Semantic Layer config."""

    operation: FieldOperationKind
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


@dataclasses.dataclass(frozen=True)
class QuestionFrame:
    """Structured interpretation of a Data Question."""

    intent: str
    metric: str
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


class NonAnswerStage(enum.StrEnum):
    """Pipeline stage that returned a Non-Answer."""

    ACCESS_CONTROLLER = "access_controller"
    DATA_REQUESTER = "data_requester"
    QUESTION_INTERPRETER = "question_interpreter"
    SEMANTIC_ROUTER = "semantic_router"


class NonAnswerReasonCode(enum.StrEnum):
    """Typed reason categories for Non-Answer Responses."""

    # Caller lacks access to the selected Curated Dataset.
    ACCESS_DENIED = "access_denied"
    # More than one Curated Dataset matches or was selected.
    AMBIGUOUS_DATASET = "ambiguous_dataset"
    # More than one Dataset Table can satisfy the Data Request.
    AMBIGUOUS_TABLE = "ambiguous_table"
    # Provider returned output that violates the required schema.
    INVALID_PROVIDER_OUTPUT = "invalid_provider_output"
    # Question Frame is missing a required business interpretation field.
    MISSING_REQUIRED_FIELD = "missing_required_field"
    # No Curated Dataset can answer the Question Frame.
    NO_MATCHING_DATASET = "no_matching_dataset"
    # No Dataset Table can satisfy the Question Frame.
    NO_MATCHING_TABLE = "no_matching_table"
    # Provider failed before returning usable output.
    PROVIDER_FAILURE = "provider_failure"
    # Provider proposed a label outside the Semantic Layer.
    UNKNOWN_SEMANTIC_LABEL = "unknown_semantic_label"
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


@dataclasses.dataclass(frozen=True)
class NonAnswer:
    """Workflow short-circuit when a stage cannot safely proceed."""

    stage: NonAnswerStage
    reason_code: NonAnswerReasonCode
    reason: str
    unresolved_ambiguities: tuple[str, ...]
    next_step: str
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
    """Trace of resolving Available Data for a Question Frame."""

    semantic_matches: tuple[SemanticMatch, ...]
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
    time_range: str
    filters: tuple[str, ...]
    freshness: str
    caveats: tuple[str, ...]
    limitations: tuple[str, ...] = ()


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

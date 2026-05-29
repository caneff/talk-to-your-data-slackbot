"""Pipeline handoff contracts for the Data Assistant."""

from __future__ import annotations

import dataclasses
import datetime
import enum
import typing

import pandas as pd

import data_assistant.semantic_layer.schema as schema

T = typing.TypeVar("T")


@dataclasses.dataclass(frozen=True)
class TimeRange:
    """Business time range used by a Question Frame and Data Request."""

    label: str
    start_date: datetime.date
    end_date: datetime.date

    def contains(self, value: datetime.date) -> bool:
        """Return whether a date is inside the bounded time range."""
        return self.start_date <= value <= self.end_date


@dataclasses.dataclass(frozen=True)
class QuestionFrame:
    """Structured interpretation of a Data Question."""

    intent: str
    metric: str
    dimension: str
    time_range: TimeRange
    filters: tuple[str, ...]
    unresolved_ambiguities: tuple[str, ...]


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
    # Question uses an intent not supported by the current workflow.
    UNSUPPORTED_INTENT = "unsupported_intent"
    # Question shape cannot be handled by the current interpreter.
    UNSUPPORTED_SHAPE = "unsupported_shape"


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
class DataRequest:
    """Constrained request for bounded Prepared Data."""

    dataset: schema.CuratedDataset
    table: schema.DatasetTable
    metric: schema.Metric
    dimension: schema.Dimension
    time_range: TimeRange
    filters: tuple[str, ...]
    output_shape: str
    result_limit: int


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
    response_kind: str


@dataclasses.dataclass(frozen=True)
class DataAssistantRun:
    """Trace of the Data Assistant path for the canonical question."""

    question_frame: QuestionFrame
    dataset_selection: DatasetSelection
    data_request: DataRequest
    prepared_data: PreparedData
    answer_draft: AnswerDraft
    final_response: FinalResponse


WorkflowResult: typing.TypeAlias = DataAssistantRun | FinalResponse

"""Pipeline handoff contracts for the Data Assistant."""

from __future__ import annotations

import dataclasses
import enum
import typing

import pandas as pd

import data_assistant.semantic_layer.schema as schema
import data_assistant.workflow.field_filters as field_filters

T = typing.TypeVar("T")

FieldFilter = field_filters.FieldFilter
FieldValue = field_filters.FieldValue
FilterMode = field_filters.FilterMode
RangeFilter = field_filters.RangeFilter
ValuesFilter = field_filters.ValuesFilter
render_filter_label = field_filters.render_filter_label


class NonAnswerStage(enum.StrEnum):
    """Pipeline stage that returned a Non-Answer."""

    ACCESS_CONTROLLER = "access_controller"
    QUESTION_INTERPRETER = "question_interpreter"
    SEMANTIC_ROUTER = "semantic_router"


class TimeScope(enum.StrEnum):
    """Resolved temporal scope for a trusted Data Question."""

    BOUNDED = "bounded"
    ALL_TIME = "all_time"


class SortDirection(enum.StrEnum):
    """Trusted rank ordering direction."""

    ASC = "asc"
    DESC = "desc"


DEFAULT_RESULT_LIMIT = 10


@dataclasses.dataclass(frozen=True)
class RankSpec:
    """Trusted ranking parameters for supported rank questions."""

    result_limit: int
    sort_direction: SortDirection


@dataclasses.dataclass(frozen=True)
class QuestionFrame:
    """Structured interpretation of a Data Question."""

    intent: str
    metric: str
    time_scope: TimeScope
    group_by_field: str | None
    field_filters: tuple[FieldFilter[str], ...]
    unresolved_ambiguities: tuple[str, ...]
    rank: RankSpec | None = None

    @property
    def filter_labels(self) -> tuple[str, ...]:
        """Return user-facing labels for row filters."""
        return tuple(
            render_filter_label(field_filter) for field_filter in self.field_filters
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
    group_by_field: schema.SemanticField | None
    field_filters: tuple[FieldFilter[schema.SemanticField], ...]


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
    group_by_field: schema.SemanticField | None
    field_filters: tuple[FieldFilter[schema.SemanticField], ...]
    output_shape: str
    result_limit: int
    rank: RankSpec | None = None

    @property
    def filter_labels(self) -> tuple[str, ...]:
        """Return user-facing labels for row filters."""
        return tuple(
            render_filter_label(field_filter) for field_filter in self.field_filters
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
    caveats: tuple[str, ...]
    limitations: tuple[str, ...] = ()
    group_by_label: str | None = None
    rank: RankSpec | None = None


@dataclasses.dataclass(frozen=True)
class TrustSummary:
    """Structured trust summary for answer and non-answer responses."""

    datasets: tuple[str, ...] = ()
    dataset_tables: tuple[str, ...] = ()
    time_range: str | None = None
    filters: tuple[str, ...] = ()
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

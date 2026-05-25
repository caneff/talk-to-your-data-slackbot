"""Pipeline handoff contracts for the Data Assistant."""

from __future__ import annotations

import dataclasses
import datetime
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
class Success(typing.Generic[T]):
    """Successful stage result."""

    value: T


@dataclasses.dataclass(frozen=True)
class NonAnswer:
    """Workflow short-circuit when a stage cannot safely proceed."""

    stage: str
    reason: str
    unresolved_ambiguities: tuple[str, ...]
    next_step: str


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


@dataclasses.dataclass(frozen=True)
class AnswerDraft:
    """Reasoning Layer answer proposal based on Prepared Data."""

    summary: str
    key_data: pd.DataFrame
    datasets_used: tuple[str, ...]
    dataset_tables_used: tuple[str, ...]
    time_range: str
    filters: tuple[str, ...]
    caveats: tuple[str, ...]


@dataclasses.dataclass(frozen=True)
class FinalResponse:
    """Plain-text Final Response prepared by the Response Composer."""

    text: str
    trust_summary: str


@dataclasses.dataclass(frozen=True)
class DataAssistantRun:
    """Trace of the Data Assistant path for the canonical question."""

    question_frame: QuestionFrame
    dataset_selection: DatasetSelection
    data_request: DataRequest
    prepared_data: PreparedData
    answer_draft: AnswerDraft
    final_response: FinalResponse


WorkflowResult: typing.TypeAlias = DataAssistantRun | NonAnswer

"""Pipeline handoff contracts for the clean commerce Data Assistant spine."""

from __future__ import annotations

import dataclasses
import datetime
import decimal

from data_slackbot.clean_commerce_spine.semantic_layer import schema


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
class DatasetSelection:
    """Semantic Router result for a Question Frame."""

    selected_datasets: tuple[schema.CuratedDataset, ...]
    match_rationale: str


@dataclasses.dataclass(frozen=True)
class DataRequest:
    """Constrained request for bounded Prepared Data."""

    curated_dataset_id: str
    table_id: str
    metric_id: str
    metric_label: str
    metric_expression: str
    dimension_id: str
    dimension_label: str
    dimension_column: str
    date_column: str
    time_range: TimeRange
    filters: tuple[str, ...]
    output_shape: str
    result_limit: int


@dataclasses.dataclass(frozen=True)
class PreparedRevenueByRegion:
    """Grouped revenue result passed to the Reasoning Layer."""

    region: str
    total_revenue: decimal.Decimal


@dataclasses.dataclass(frozen=True)
class PreparedData:
    """Bounded result produced from a Data Request."""

    request: DataRequest
    rows: tuple[PreparedRevenueByRegion, ...]
    source_row_count: int


@dataclasses.dataclass(frozen=True)
class AnswerDraft:
    """Reasoning Layer answer proposal based on Prepared Data."""

    summary: str
    key_numbers: tuple[PreparedRevenueByRegion, ...]
    datasets_used: tuple[str, ...]
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
    """Trace of the clean Data Assistant path for the canonical question."""

    question_frame: QuestionFrame
    dataset_selection: DatasetSelection
    data_request: DataRequest
    prepared_data: PreparedData
    answer_draft: AnswerDraft
    final_response: FinalResponse

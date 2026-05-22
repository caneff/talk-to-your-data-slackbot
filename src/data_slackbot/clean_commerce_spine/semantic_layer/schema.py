"""Semantic Layer config schema models."""

from __future__ import annotations

import dataclasses
import datetime


@dataclasses.dataclass(frozen=True)
class Freshness:
    """Freshness context for a Curated Dataset."""

    as_of: datetime.date
    description: str


@dataclasses.dataclass(frozen=True)
class CuratedDataset:
    """Approved business data product available through the Semantic Layer."""

    dataset_id: str
    name: str
    tables: tuple[str, ...]
    information_types: tuple[str, ...]
    freshness: Freshness
    example_questions: tuple[str, ...]


@dataclasses.dataclass(frozen=True)
class TableColumn:
    """Physical column available in a Dataset Table."""

    column_id: str
    data_type: str
    semantic_role: str | None


@dataclasses.dataclass(frozen=True)
class Metric:
    """Business metric defined on a Dataset Table."""

    metric_id: str
    label: str
    expression: str


@dataclasses.dataclass(frozen=True)
class Dimension:
    """Business dimension defined on a Dataset Table."""

    dimension_id: str
    label: str
    column: str


@dataclasses.dataclass(frozen=True)
class DatasetTable:
    """Dataset Table definition loaded from the Semantic Layer."""

    table_id: str
    dataset_id: str
    description: str
    date_column: str
    columns: tuple[TableColumn, ...]
    metrics: tuple[Metric, ...]
    dimensions: tuple[Dimension, ...]


@dataclasses.dataclass(frozen=True)
class SemanticLayer:
    """Semantic Layer definitions loaded from versioned config."""

    datasets: tuple[CuratedDataset, ...]
    tables: tuple[DatasetTable, ...]

"""Semantic Layer config schema models."""

from __future__ import annotations

import datetime

import pydantic


class _SemanticLayerModel(pydantic.BaseModel):
    model_config = pydantic.ConfigDict(frozen=True)


class Freshness(_SemanticLayerModel):
    """Freshness context for a Curated Dataset."""

    as_of: datetime.date
    description: str


class CuratedDataset(_SemanticLayerModel):
    """Approved business data product available through the Semantic Layer."""

    dataset_id: str
    name: str
    tables: tuple[str, ...]
    information_types: tuple[str, ...]
    freshness: Freshness
    example_questions: tuple[str, ...]


class TableColumn(_SemanticLayerModel):
    """Physical column available in a Dataset Table."""

    column_id: str
    data_type: str
    semantic_role: str | None = None


class Metric(_SemanticLayerModel):
    """Business metric defined on a Dataset Table."""

    metric_id: str
    label: str
    expression: str


class Dimension(_SemanticLayerModel):
    """Business dimension defined on a Dataset Table."""

    dimension_id: str
    label: str
    column: str


class DatasetTable(_SemanticLayerModel):
    """Dataset Table definition loaded from the Semantic Layer."""

    table_id: str
    dataset_id: str
    description: str
    date_column: str
    columns: tuple[TableColumn, ...]
    metrics: tuple[Metric, ...]
    dimensions: tuple[Dimension, ...]


class SemanticLayer(_SemanticLayerModel):
    """Semantic Layer definitions loaded from versioned config."""

    datasets: tuple[CuratedDataset, ...]
    tables: tuple[DatasetTable, ...]

"""Semantic Layer config schema models."""

from __future__ import annotations

import datetime
import typing

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
    source_column: str


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

    @pydantic.model_validator(mode="after")
    def _validate_references(self) -> typing.Self:
        column_ids = {column.column_id for column in self.columns}
        if self.date_column not in column_ids:
            msg = f"Date column is not listed in columns: {self.date_column}"
            raise ValueError(msg)
        for dimension in self.dimensions:
            if dimension.column not in column_ids:
                msg = f"Dimension column is not listed in columns: {dimension.column}"
                raise ValueError(msg)
        for metric in self.metrics:
            if metric.source_column not in column_ids:
                msg = (
                    "Metric source column is not listed in columns: "
                    f"{metric.source_column}"
                )
                raise ValueError(msg)
        return self


class SemanticLayer(_SemanticLayerModel):
    """Semantic Layer definitions loaded from versioned config."""

    datasets: tuple[CuratedDataset, ...]
    tables: tuple[DatasetTable, ...]

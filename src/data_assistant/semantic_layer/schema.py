"""Semantic Layer config schema models."""

from __future__ import annotations

import datetime
import enum
import typing

import pydantic


class _SemanticLayerModel(pydantic.BaseModel):
    model_config = pydantic.ConfigDict(frozen=True)


class DatasetAccess(_SemanticLayerModel):
    """Dataset-level access rules for a Curated Dataset."""

    allowed_identity_ids: tuple[str, ...]


class CuratedDataset(_SemanticLayerModel):
    """Approved business data product available through the Semantic Layer."""

    dataset_id: str
    name: str
    tables: tuple[str, ...]
    information_types: tuple[str, ...]
    example_questions: tuple[str, ...]
    as_of_date: datetime.date | None = None
    dataset_access: DatasetAccess = DatasetAccess(allowed_identity_ids=())


class TableColumn(_SemanticLayerModel):
    """Physical column available in a Dataset Table."""

    column_id: str
    data_type: str
    semantic_role: str | None = None


class MetricKind(enum.StrEnum):
    """Presentation kind for metric values."""

    MONEY = "money"
    COUNT = "count"


class Metric(_SemanticLayerModel):
    """Business metric defined on a Dataset Table."""

    metric_id: str
    label: str
    aliases: tuple[str, ...] = ()
    expression: str
    source_column: str
    kind: MetricKind


class FieldOperation(enum.StrEnum):
    """Allowed business operation kinds for a Semantic Field."""

    GROUP_BY = "group_by"
    RANGE_FILTER = "range_filter"
    INCLUDE_FILTER = "include_filter"
    EXCLUDE_FILTER = "exclude_filter"


class DataType(enum.StrEnum):
    """Value type used to validate and coerce Semantic Field filter values."""

    DATE = "date"
    DECIMAL = "decimal"
    STRING = "string"


class SemanticField(_SemanticLayerModel):
    """Business field defined on a Dataset Table."""

    field_id: str
    label: str
    source_column: str
    data_type: DataType
    operations: tuple[FieldOperation, ...]


class DatasetTable(_SemanticLayerModel):
    """Dataset Table definition loaded from the Semantic Layer."""

    table_id: str
    dataset_id: str
    description: str
    columns: tuple[TableColumn, ...]
    metrics: tuple[Metric, ...]
    fields: tuple[SemanticField, ...]

    @pydantic.model_validator(mode="after")
    def _validate_references(self) -> typing.Self:
        column_ids = {column.column_id for column in self.columns}
        for field in self.fields:
            if field.source_column not in column_ids:
                msg = (
                    "Field source column is not listed in columns: "
                    f"{field.source_column}"
                )
                raise ValueError(msg)
        for metric in self.metrics:
            if metric.source_column not in column_ids:
                msg = (
                    "Metric source column is not listed in columns: "
                    f"{metric.source_column}"
                )
                raise ValueError(msg)
        return self

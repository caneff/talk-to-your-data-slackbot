from __future__ import annotations

import collections.abc
import datetime

import data_assistant.semantic_layer.catalog as semantic_layer_catalog
import data_assistant.semantic_layer.schema as schema

_DEFAULT_COLUMNS = {
    "order_date": "date",
    "region": "varchar",
    "revenue": "decimal",
}
_DEFAULT_METRICS = (
    schema.Metric(
        metric_id="total_revenue",
        label="total revenue",
        expression="sum(revenue)",
        source_column="revenue",
        kind=schema.MetricKind.MONEY,
    ),
)
_DEFAULT_FIELDS = (
    schema.SemanticField(
        field_id="order_date",
        label="order date",
        source_column="order_date",
        data_type=schema.DataType.DATE,
        operations=(
            schema.FieldOperation.INCLUDE_FILTER,
            schema.FieldOperation.EXCLUDE_FILTER,
            schema.FieldOperation.RANGE_FILTER,
        ),
    ),
    schema.SemanticField(
        field_id="region",
        label="region",
        source_column="region",
        data_type=schema.DataType.STRING,
        operations=(
            schema.FieldOperation.GROUP_BY,
            schema.FieldOperation.INCLUDE_FILTER,
            schema.FieldOperation.EXCLUDE_FILTER,
        ),
    ),
)


def semantic_layer_with_table(
    *,
    table_id: str = "orders",
    dataset_id: str = "commerce",
    description: str = "Orders table.",
    columns: collections.abc.Mapping[str, str] = _DEFAULT_COLUMNS,
    metrics: tuple[schema.Metric, ...] = _DEFAULT_METRICS,
    fields: tuple[schema.SemanticField, ...] = _DEFAULT_FIELDS,
) -> semantic_layer_catalog.SemanticLayerCatalog:
    return semantic_layer_catalog.SemanticLayerCatalog(
        datasets=(
            schema.CuratedDataset(
                dataset_id=dataset_id,
                name=dataset_id.title(),
                tables=(table_id,),
                information_types=("financial",),
                freshness=schema.Freshness(
                    as_of=datetime.date(2026, 1, 31),
                    description="Daily refresh.",
                ),
                example_questions=("What was total revenue?",),
            ),
        ),
        tables=(
            schema.DatasetTable(
                table_id=table_id,
                dataset_id=dataset_id,
                description=description,
                columns=tuple(
                    schema.TableColumn(column_id=column_id, data_type=data_type)
                    for column_id, data_type in columns.items()
                ),
                metrics=metrics,
                fields=fields,
            ),
        ),
    )

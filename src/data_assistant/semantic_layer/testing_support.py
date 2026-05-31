from __future__ import annotations

import collections.abc

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
    ),
)
_DEFAULT_FIELDS = (
    schema.SemanticField(
        field_id="order_date",
        label="order date",
        source_column="order_date",
        data_type="date",
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
        data_type="string",
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
    date_column: str = "order_date",
    columns: collections.abc.Mapping[str, str] = _DEFAULT_COLUMNS,
    metrics: tuple[schema.Metric, ...] = _DEFAULT_METRICS,
    fields: tuple[schema.SemanticField, ...] = _DEFAULT_FIELDS,
) -> schema.SemanticLayer:
    return schema.SemanticLayer(
        datasets=(),
        tables=(
            schema.DatasetTable(
                table_id=table_id,
                dataset_id=dataset_id,
                description=description,
                date_column=date_column,
                columns=tuple(
                    schema.TableColumn(column_id=column_id, data_type=data_type)
                    for column_id, data_type in columns.items()
                ),
                metrics=metrics,
                fields=fields,
            ),
        ),
    )

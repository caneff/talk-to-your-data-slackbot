import pytest

import data_assistant.semantic_layer.loader as semantic_layer_loader
import data_assistant.semantic_layer.schema as schema


def test_semantic_layer_loads_dataset_table_relationship() -> None:
    loaded_semantic_layer = semantic_layer_loader.load_semantic_layer()

    dataset = semantic_layer_loader.find_dataset("commerce", loaded_semantic_layer)
    tables = semantic_layer_loader.tables_for_dataset(dataset, loaded_semantic_layer)
    table_ids = {table.table_id for table in tables}

    assert dataset.tables == ("orders", "customers")
    assert dataset.dataset_access.allowed_identity_ids == (
        "employee_123",
        "local_development_user",
    )
    assert table_ids == {"orders", "customers"}

    customers = semantic_layer_loader.find_table("customers", loaded_semantic_layer)
    column_ids = {column.column_id for column in customers.columns}
    metrics_by_id = {metric.metric_id: metric for metric in customers.metrics}
    dimensions_by_id = {
        dimension.dimension_id: dimension for dimension in customers.dimensions
    }
    assert customers.dataset_id == "commerce"
    assert customers.date_column == "created_date"
    assert column_ids == {"created_date", "customer_id", "customer_region"}
    assert metrics_by_id["customer_count"].label == "customer count"
    assert metrics_by_id["customer_count"].expression == "count(customer_id)"
    assert metrics_by_id["customer_count"].source_column == "customer_id"
    assert dimensions_by_id["customer_region"].label == "customer region"
    assert dimensions_by_id["customer_region"].column == "customer_region"

    orders = semantic_layer_loader.find_table("orders", loaded_semantic_layer)
    orders_metrics_by_id = {metric.metric_id: metric for metric in orders.metrics}
    assert orders_metrics_by_id["total_revenue"].source_column == "revenue"


def test_dataset_table_rejects_metric_source_column_outside_columns() -> None:
    with pytest.raises(ValueError, match="Metric source column is not listed"):
        schema.DatasetTable(
            table_id="orders",
            dataset_id="commerce",
            description="Clean commerce order facts.",
            date_column="order_date",
            columns=(
                schema.TableColumn(column_id="order_date", data_type="date"),
                schema.TableColumn(column_id="region", data_type="string"),
                schema.TableColumn(column_id="revenue", data_type="decimal"),
            ),
            metrics=(
                schema.Metric(
                    metric_id="total_revenue",
                    label="total revenue",
                    expression="sum(revenue)",
                    source_column="missing_revenue",
                ),
            ),
            dimensions=(
                schema.Dimension(
                    dimension_id="region",
                    label="region",
                    column="region",
                ),
            ),
        )

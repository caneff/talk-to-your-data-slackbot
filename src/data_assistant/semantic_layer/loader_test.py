import pytest

import data_assistant.semantic_layer.loader as semantic_layer_loader
import data_assistant.semantic_layer.schema as schema


def test_semantic_layer_loads_dataset_table_relationship() -> None:
    loaded_semantic_layer = semantic_layer_loader.load_semantic_layer()

    dataset = loaded_semantic_layer.find_dataset("retail_ops")
    tables = loaded_semantic_layer.tables_for_dataset_id("retail_ops")
    table_ids = {table.table_id for table in tables}

    assert dataset.name == "Retail Operations"
    assert dataset.tables == (
        "demo_orders",
        "demo_order_lines",
        "demo_customers",
        "demo_products",
        "demo_stores",
        "demo_support_tickets",
        "demo_inventory_snapshots",
    )
    assert dataset.dataset_access.allowed_identity_ids == (
        "employee_123",
        "local_development_user",
    )
    assert dataset.example_questions == (
        "What was total net revenue by store region in Q1 2026?",
        "What was gross margin by product category in March 2026?",
        "What was support ticket count by issue category in April 2026?",
        "Which product categories had the most stockout days in May 2026?",
    )
    assert table_ids == {
        "demo_orders",
        "demo_order_lines",
        "demo_customers",
        "demo_products",
        "demo_stores",
        "demo_support_tickets",
        "demo_inventory_snapshots",
    }

    customers = loaded_semantic_layer.find_table("demo_customers")
    column_ids = {column.column_id for column in customers.columns}
    metrics_by_id = {metric.metric_id: metric for metric in customers.metrics}
    fields_by_id = {field.field_id: field for field in customers.fields}
    assert customers.dataset_id == "retail_ops"
    assert column_ids == {
        "customer_id",
        "created_date",
        "customer_segment",
        "customer_region",
        "loyalty_tier",
        "acquisition_channel",
    }
    assert metrics_by_id["customer_count"].label == "customer count"
    assert metrics_by_id["customer_count"].expression == "count(customer_id)"
    assert metrics_by_id["customer_count"].source_column == "customer_id"
    assert metrics_by_id["customer_count"].kind == schema.MetricKind.COUNT
    assert fields_by_id["customer_region"].label == "customer region"
    assert fields_by_id["customer_region"].source_column == "customer_region"
    assert schema.FieldOperation.GROUP_BY in fields_by_id["customer_region"].operations

    orders = loaded_semantic_layer.find_table("demo_orders")
    orders_metrics_by_id = {metric.metric_id: metric for metric in orders.metrics}
    assert orders_metrics_by_id["total_net_revenue"].source_column == "net_revenue"
    assert orders_metrics_by_id["total_net_revenue"].kind == schema.MetricKind.MONEY
    assert orders_metrics_by_id["order_count"].aliases == ("order volume",)
    assert orders_metrics_by_id["total_discount_amount"].aliases == ("discounts",)

    support_tickets = loaded_semantic_layer.find_table("demo_support_tickets")
    support_metrics_by_id = {
        metric.metric_id: metric for metric in support_tickets.metrics
    }
    assert support_metrics_by_id["support_ticket_count"].aliases == ("tickets",)


def test_dataset_table_rejects_metric_source_column_outside_columns() -> None:
    with pytest.raises(ValueError, match="Metric source column is not listed"):
        schema.DatasetTable(
            table_id="orders",
            dataset_id="retail_ops",
            description="Clean retail order facts.",
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
                    kind=schema.MetricKind.MONEY,
                ),
            ),
            fields=(
                schema.SemanticField(
                    field_id="region",
                    label="region",
                    source_column="region",
                    data_type=schema.DataType.STRING,
                    operations=(schema.FieldOperation.GROUP_BY,),
                ),
            ),
        )

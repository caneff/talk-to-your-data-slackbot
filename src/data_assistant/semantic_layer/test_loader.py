import data_assistant.semantic_layer.loader as semantic_layer_loader


def test_semantic_layer_loads_dataset_table_relationship() -> None:
    loaded_semantic_layer = semantic_layer_loader.load_semantic_layer()

    dataset = semantic_layer_loader.find_dataset("commerce", loaded_semantic_layer)
    tables = semantic_layer_loader.tables_for_dataset(dataset, loaded_semantic_layer)
    table_ids = {table.table_id for table in tables}

    assert dataset.tables == ("orders", "customers")
    assert table_ids == {"orders", "customers"}

    customers = semantic_layer_loader.find_table("customers", loaded_semantic_layer)
    column_ids = {column.column_id for column in customers.columns}
    metric_ids = {metric.metric_id for metric in customers.metrics}
    dimension_ids = {dimension.dimension_id for dimension in customers.dimensions}
    assert customers.dataset_id == "commerce"
    assert customers.date_column == "created_date"
    assert column_ids == {"created_date", "customer_id", "customer_region"}
    assert metric_ids == {"customer_count"}
    assert dimension_ids == {"customer_region"}

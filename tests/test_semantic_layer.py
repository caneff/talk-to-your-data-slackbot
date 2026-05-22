import datetime

from data_slackbot.clean_commerce_spine import semantic_layer


def test_semantic_layer_loads_dataset_and_table_yaml() -> None:
    loaded_semantic_layer = semantic_layer.load_semantic_layer()

    dataset = semantic_layer.find_dataset("commerce", loaded_semantic_layer)
    table = semantic_layer.find_table("orders", loaded_semantic_layer)

    assert dataset.name == "Commerce Revenue"
    assert dataset.tables == ("orders",)
    assert dataset.information_types == (
        "revenue",
        "regional performance",
        "order activity",
    )
    assert dataset.freshness.as_of == datetime.date(2026, 1, 31)
    assert dataset.example_questions == (
        "What was total revenue by region in January 2026?",
    )
    assert table.dataset_id == "commerce"
    assert table.date_column == "order_date"
    assert table.metrics[0].label == "total revenue"
    assert table.dimensions[0].column == "region"

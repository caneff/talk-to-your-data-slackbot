from data_slackbot.clean_commerce_spine import semantic_layer


def test_semantic_layer_loads_dataset_table_relationship() -> None:
    loaded_semantic_layer = semantic_layer.load_semantic_layer()

    dataset = semantic_layer.find_dataset("commerce", loaded_semantic_layer)
    tables = semantic_layer.tables_for_dataset(dataset, loaded_semantic_layer)

    assert len(tables) == 1
    assert tables[0].table_id == "orders"

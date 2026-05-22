import data_slackbot.data_assistant.semantic_layer.loader as semantic_layer_loader


def test_semantic_layer_loads_dataset_table_relationship() -> None:
    loaded_semantic_layer = semantic_layer_loader.load_semantic_layer()

    dataset = semantic_layer_loader.find_dataset("commerce", loaded_semantic_layer)
    tables = semantic_layer_loader.tables_for_dataset(dataset, loaded_semantic_layer)

    assert len(tables) == 1
    assert tables[0].table_id == "orders"

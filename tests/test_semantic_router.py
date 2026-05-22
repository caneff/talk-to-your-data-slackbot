from data_slackbot.clean_commerce_spine import contracts


def test_dataset_selection_chooses_one_curated_dataset_with_rationale(
    dataset_selection: contracts.DatasetSelection,
) -> None:
    assert len(dataset_selection.selected_datasets) == 1
    assert dataset_selection.selected_datasets[0].dataset_id == "commerce"
    assert "total revenue metric and region dimension" in (
        dataset_selection.match_rationale
    )

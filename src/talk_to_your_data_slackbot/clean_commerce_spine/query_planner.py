"""Query Planner step for clean commerce Data Request creation."""

from __future__ import annotations

from talk_to_your_data_slackbot.clean_commerce_spine import contracts


def create_data_request(
    question_frame: contracts.QuestionFrame,
    dataset_selection: contracts.DatasetSelection,
) -> contracts.DataRequest:
    """Create the Data Request for revenue grouped by region."""
    if len(dataset_selection.selected_datasets) != 1:
        msg = "A clean Data Request requires exactly one Curated Dataset."
        raise ValueError(msg)

    dataset = dataset_selection.selected_datasets[0]
    return contracts.DataRequest(
        curated_dataset_id=dataset.dataset_id,
        selected_tables=("orders",),
        metric=question_frame.metric,
        group_by=(question_frame.dimension,),
        time_range=question_frame.time_range,
        filters=question_frame.filters,
        output_shape="total revenue grouped by region",
        result_limit=10,
    )

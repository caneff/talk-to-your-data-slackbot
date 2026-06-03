"""Data Requester step for Data Assistant Data Request creation."""

from __future__ import annotations

import data_assistant.workflow.contracts as contracts

DEFAULT_RESULT_LIMIT = 10


def create_data_request(
    question_frame: contracts.QuestionFrame,
    available_data_resolution: contracts.AvailableDataResolution,
) -> contracts.DataRequest:
    """Create the Data Request from resolved Available Data."""
    resolved_match = available_data_resolution.resolved_match
    del question_frame
    return contracts.DataRequest(
        dataset=resolved_match.dataset,
        table=resolved_match.table,
        metric=resolved_match.metric,
        group_by_field=resolved_match.group_by_field,
        field_filters=resolved_match.field_filters,
        output_shape=_output_shape(resolved_match),
        result_limit=DEFAULT_RESULT_LIMIT,
    )


def _output_shape(match: contracts.SemanticMatch) -> str:
    if match.group_by_field is None:
        return match.metric.label
    return f"{match.metric.label} grouped by {match.group_by_field.label}"

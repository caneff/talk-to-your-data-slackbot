"""Prepared Data step for clean commerce revenue by region."""

from __future__ import annotations

import decimal

from data_slackbot.clean_commerce_spine import contracts
from data_slackbot.clean_commerce_spine import (
    semantic_layer as semantic_layer_module,
)


def prepare_data(
    data_request: contracts.DataRequest,
    semantic_layer: contracts.SemanticLayer,
) -> contracts.PreparedData:
    """Produce bounded grouped Prepared Data for clean commerce rows."""
    dataset = semantic_layer_module.find_dataset(
        data_request.curated_dataset_id,
        semantic_layer,
    )
    totals: dict[str, decimal.Decimal] = {}
    source_row_count = 0

    for row in dataset.rows:
        if data_request.time_range.contains(row.order_date):
            source_row_count += 1
            totals[row.region] = (
                totals.get(row.region, decimal.Decimal("0.00")) + row.revenue
            )

    grouped_rows = tuple(
        contracts.PreparedRevenueByRegion(region=region, total_revenue=total)
        for region, total in sorted(
            totals.items(),
            key=lambda item: (-item[1], item[0]),
        )
    )[: data_request.result_limit]

    return contracts.PreparedData(
        request=data_request,
        rows=grouped_rows,
        source_row_count=source_row_count,
    )

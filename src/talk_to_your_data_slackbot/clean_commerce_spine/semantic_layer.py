"""In-memory Semantic Layer fixture for clean commerce revenue."""

from __future__ import annotations

import datetime
import decimal

from talk_to_your_data_slackbot.clean_commerce_spine import contracts


def default_semantic_layer() -> contracts.SemanticLayer:
    """Return the clean in-memory Semantic Layer fixture for issue #8."""
    commerce_dataset = contracts.CuratedDataset(
        dataset_id="commerce",
        name="Commerce Revenue",
        tables=("orders",),
        metrics=("total revenue",),
        dimensions=("region",),
        freshness="clean fixture rows for January 2026",
        rows=(
            contracts.CommerceRow(
                order_date=datetime.date(2026, 1, 3),
                region="North",
                revenue=decimal.Decimal("1200.00"),
            ),
            contracts.CommerceRow(
                order_date=datetime.date(2026, 1, 8),
                region="South",
                revenue=decimal.Decimal("850.00"),
            ),
            contracts.CommerceRow(
                order_date=datetime.date(2026, 1, 15),
                region="West",
                revenue=decimal.Decimal("1600.00"),
            ),
            contracts.CommerceRow(
                order_date=datetime.date(2026, 1, 22),
                region="North",
                revenue=decimal.Decimal("300.00"),
            ),
            contracts.CommerceRow(
                order_date=datetime.date(2026, 1, 28),
                region="East",
                revenue=decimal.Decimal("950.00"),
            ),
        ),
    )
    return contracts.SemanticLayer(datasets=(commerce_dataset,))


def find_dataset(
    dataset_id: str,
    semantic_layer: contracts.SemanticLayer,
) -> contracts.CuratedDataset:
    """Find a Curated Dataset by id."""
    for dataset in semantic_layer.datasets:
        if dataset.dataset_id == dataset_id:
            return dataset

    msg = f"Curated Dataset not found: {dataset_id}"
    raise ValueError(msg)

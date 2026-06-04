import pytest

import data_assistant.semantic_layer.schema as schema
from data_assistant.semantic_layer.catalog import SemanticLayerCatalog


def test_catalog_rejects_duplicate_dataset_ids() -> None:
    orders = _table(table_id="orders", dataset_id="retail_ops")

    with pytest.raises(ValueError, match="Duplicate Curated Dataset ids: retail_ops"):
        SemanticLayerCatalog(
            datasets=(
                _dataset(dataset_id="retail_ops", table_ids=("orders",)),
                _dataset(dataset_id="retail_ops", table_ids=("orders",)),
            ),
            tables=(orders,),
        )


def test_catalog_rejects_duplicate_table_ids() -> None:
    with pytest.raises(ValueError, match="Duplicate Dataset Table ids: orders"):
        SemanticLayerCatalog(
            datasets=(_dataset(dataset_id="retail_ops", table_ids=("orders",)),),
            tables=(
                _table(table_id="orders", dataset_id="retail_ops"),
                _table(table_id="orders", dataset_id="retail_ops"),
            ),
        )


def test_catalog_aggregates_duplicate_and_relationship_errors() -> None:
    with pytest.raises(ValueError) as exc_info:
        SemanticLayerCatalog(
            datasets=(
                _dataset(dataset_id="retail_ops", table_ids=("orders", "missing")),
                _dataset(dataset_id="retail_ops", table_ids=("orders", "missing")),
            ),
            tables=(
                _table(table_id="orders", dataset_id="retail_ops"),
                _table(table_id="orders", dataset_id="retail_ops"),
                _table(table_id="orphan", dataset_id="orphan"),
            ),
        )

    assert str(exc_info.value) == "\n".join(
        (
            "Duplicate Curated Dataset ids: retail_ops",
            "Duplicate Dataset Table ids: orders",
            "Unknown Dataset Table refs for Curated Dataset retail_ops: missing",
            "Dataset Table refs listed by multiple Curated Datasets: orders",
            "Orphan Dataset Tables not listed by any Curated Dataset: orphan",
        )
    )


def test_catalog_aggregates_structural_relationship_errors() -> None:
    with pytest.raises(ValueError) as exc_info:
        SemanticLayerCatalog(
            datasets=(
                _dataset(
                    dataset_id="retail_ops",
                    table_ids=("orders", "missing", "shared"),
                ),
                _dataset(
                    dataset_id="support",
                    table_ids=("shared", "support_orders"),
                ),
            ),
            tables=(
                _table(table_id="orders", dataset_id="retail_ops"),
                _table(table_id="shared", dataset_id="retail_ops"),
                _table(table_id="support_orders", dataset_id="retail_ops"),
                _table(table_id="orphan", dataset_id="orphan"),
            ),
        )

    assert str(exc_info.value) == "\n".join(
        (
            "Unknown Dataset Table refs for Curated Dataset retail_ops: missing",
            (
                "Curated Dataset support lists Dataset Table shared, but "
                "table.dataset_id is retail_ops"
            ),
            (
                "Curated Dataset support lists Dataset Table support_orders, "
                "but table.dataset_id is retail_ops"
            ),
            "Dataset Table refs listed by multiple Curated Datasets: shared",
            "Orphan Dataset Tables not listed by any Curated Dataset: orphan",
        )
    )


def test_catalog_lookup_methods_reject_invalid_ids() -> None:
    catalog = SemanticLayerCatalog(
        datasets=(_dataset(dataset_id="retail_ops", table_ids=("orders",)),),
        tables=(_table(table_id="orders", dataset_id="retail_ops"),),
    )

    with pytest.raises(ValueError, match="Curated Dataset not found: missing"):
        catalog.find_dataset("missing")

    with pytest.raises(ValueError, match="Dataset Table not found: missing"):
        catalog.find_table("missing")

    with pytest.raises(ValueError, match="Curated Dataset not found: missing"):
        catalog.tables_for_dataset_id("missing")


def test_catalog_rejects_duplicate_metric_aliases_within_one_table() -> None:
    with pytest.raises(
        ValueError,
        match="Duplicate Metric aliases in Dataset Table orders: order volume",
    ):
        SemanticLayerCatalog(
            datasets=(_dataset(dataset_id="retail_ops", table_ids=("orders",)),),
            tables=(
                _table(
                    table_id="orders",
                    dataset_id="retail_ops",
                    metrics=(
                        _metric(
                            metric_id="order_count",
                            label="order count",
                            aliases=("order volume",),
                        ),
                        _metric(
                            metric_id="gross_margin",
                            label="gross margin",
                            aliases=("order volume",),
                        ),
                    ),
                ),
            ),
        )


def test_catalog_rejects_metric_alias_matching_other_metric_label() -> None:
    with pytest.raises(
        ValueError,
        match=(
            "Metric aliases collide with canonical Metric labels in Dataset Table "
            "orders: order count"
        ),
    ):
        SemanticLayerCatalog(
            datasets=(_dataset(dataset_id="retail_ops", table_ids=("orders",)),),
            tables=(
                _table(
                    table_id="orders",
                    dataset_id="retail_ops",
                    metrics=(
                        _metric(
                            metric_id="total_orders",
                            label="total orders",
                            aliases=("order count",),
                        ),
                        _metric(
                            metric_id="order_count",
                            label="order count",
                            aliases=("orders",),
                        ),
                    ),
                ),
            ),
        )


def test_catalog_allows_metric_alias_reuse_across_tables() -> None:
    catalog = SemanticLayerCatalog(
        datasets=(
            _dataset(
                dataset_id="retail_ops",
                table_ids=("orders", "support_tickets"),
            ),
        ),
        tables=(
            _table(
                table_id="orders",
                dataset_id="retail_ops",
                metrics=(
                    _metric(
                        metric_id="order_count",
                        label="order count",
                        aliases=("order volume",),
                    ),
                ),
            ),
            _table(
                table_id="support_tickets",
                dataset_id="retail_ops",
                metrics=(
                    _metric(
                        metric_id="support_ticket_count",
                        label="support ticket count",
                        aliases=("order volume",),
                    ),
                ),
            ),
        ),
    )

    assert len(catalog.tables) == 2


def _dataset(
    *,
    dataset_id: str,
    table_ids: tuple[str, ...],
) -> schema.CuratedDataset:
    return schema.CuratedDataset(
        dataset_id=dataset_id,
        name=dataset_id.title(),
        tables=table_ids,
        information_types=("financial",),
        example_questions=("What was total revenue?",),
    )


def _table(
    *,
    table_id: str,
    dataset_id: str,
    metrics: tuple[schema.Metric, ...] | None = None,
) -> schema.DatasetTable:
    return schema.DatasetTable(
        table_id=table_id,
        dataset_id=dataset_id,
        description=f"{table_id} table.",
        columns=(
            schema.TableColumn(column_id="order_date", data_type="date"),
            schema.TableColumn(column_id="region", data_type="string"),
            schema.TableColumn(column_id="revenue", data_type="decimal"),
        ),
        metrics=metrics or (_metric(),),
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


def _metric(
    *,
    metric_id: str = "total_revenue",
    label: str = "total revenue",
    aliases: tuple[str, ...] = (),
) -> schema.Metric:
    return schema.Metric(
        metric_id=metric_id,
        label=label,
        aliases=aliases,
        expression="sum(revenue)",
        source_column="revenue",
        kind=schema.MetricKind.MONEY,
    )

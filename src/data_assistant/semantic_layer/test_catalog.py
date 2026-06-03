import pytest

import data_assistant.semantic_layer.schema as schema
from data_assistant.semantic_layer.catalog import SemanticLayerCatalog


def test_catalog_rejects_duplicate_dataset_ids() -> None:
    orders = _table(table_id="orders", dataset_id="commerce")

    with pytest.raises(ValueError, match="Duplicate Curated Dataset ids: commerce"):
        SemanticLayerCatalog(
            datasets=(
                _dataset(dataset_id="commerce", table_ids=("orders",)),
                _dataset(dataset_id="commerce", table_ids=("orders",)),
            ),
            tables=(orders,),
        )


def test_catalog_rejects_duplicate_table_ids() -> None:
    with pytest.raises(ValueError, match="Duplicate Dataset Table ids: orders"):
        SemanticLayerCatalog(
            datasets=(_dataset(dataset_id="commerce", table_ids=("orders",)),),
            tables=(
                _table(table_id="orders", dataset_id="commerce"),
                _table(table_id="orders", dataset_id="commerce"),
            ),
        )


def test_catalog_aggregates_duplicate_and_relationship_errors() -> None:
    with pytest.raises(ValueError) as exc_info:
        SemanticLayerCatalog(
            datasets=(
                _dataset(dataset_id="commerce", table_ids=("orders", "missing")),
                _dataset(dataset_id="commerce", table_ids=("orders", "missing")),
            ),
            tables=(
                _table(table_id="orders", dataset_id="commerce"),
                _table(table_id="orders", dataset_id="commerce"),
                _table(table_id="orphan", dataset_id="orphan"),
            ),
        )

    assert str(exc_info.value) == "\n".join(
        (
            "Duplicate Curated Dataset ids: commerce",
            "Duplicate Dataset Table ids: orders",
            "Unknown Dataset Table refs for Curated Dataset commerce: missing",
            "Dataset Table refs listed by multiple Curated Datasets: orders",
            "Orphan Dataset Tables not listed by any Curated Dataset: orphan",
        )
    )


def test_catalog_aggregates_structural_relationship_errors() -> None:
    with pytest.raises(ValueError) as exc_info:
        SemanticLayerCatalog(
            datasets=(
                _dataset(
                    dataset_id="commerce",
                    table_ids=("orders", "missing", "shared"),
                ),
                _dataset(
                    dataset_id="support",
                    table_ids=("shared", "support_orders"),
                ),
            ),
            tables=(
                _table(table_id="orders", dataset_id="commerce"),
                _table(table_id="shared", dataset_id="commerce"),
                _table(table_id="support_orders", dataset_id="commerce"),
                _table(table_id="orphan", dataset_id="orphan"),
            ),
        )

    assert str(exc_info.value) == "\n".join(
        (
            "Unknown Dataset Table refs for Curated Dataset commerce: missing",
            (
                "Curated Dataset support lists Dataset Table shared, but "
                "table.dataset_id is commerce"
            ),
            (
                "Curated Dataset support lists Dataset Table support_orders, "
                "but table.dataset_id is commerce"
            ),
            "Dataset Table refs listed by multiple Curated Datasets: shared",
            "Orphan Dataset Tables not listed by any Curated Dataset: orphan",
        )
    )


def test_catalog_lookup_methods_reject_invalid_ids() -> None:
    catalog = SemanticLayerCatalog(
        datasets=(_dataset(dataset_id="commerce", table_ids=("orders",)),),
        tables=(_table(table_id="orders", dataset_id="commerce"),),
    )

    with pytest.raises(ValueError, match="Curated Dataset not found: missing"):
        catalog.find_dataset("missing")

    with pytest.raises(ValueError, match="Dataset Table not found: missing"):
        catalog.find_table("missing")

    with pytest.raises(ValueError, match="Curated Dataset not found: missing"):
        catalog.tables_for_dataset_id("missing")


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
        metrics=(
            schema.Metric(
                metric_id="total_revenue",
                label="total revenue",
                expression="sum(revenue)",
                source_column="revenue",
                kind=schema.MetricKind.MONEY,
            ),
        ),
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

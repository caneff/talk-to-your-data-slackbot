"""Validated Semantic Layer catalog."""

from __future__ import annotations

import collections
import collections.abc
import dataclasses

import data_assistant.semantic_layer.schema as schema


@dataclasses.dataclass(frozen=True)
class SemanticLayerCatalog:
    """Immutable validated Semantic Layer definitions."""

    datasets: tuple[schema.CuratedDataset, ...]
    tables: tuple[schema.DatasetTable, ...]

    def __post_init__(self) -> None:
        errors: list[str] = []
        duplicate_dataset_ids = _duplicate_ids(
            dataset.dataset_id for dataset in self.datasets
        )
        if duplicate_dataset_ids:
            errors.append(
                "Duplicate Curated Dataset ids: " + ", ".join(duplicate_dataset_ids)
            )
        duplicate_table_ids = _duplicate_ids(table.table_id for table in self.tables)
        if duplicate_table_ids:
            errors.append(
                "Duplicate Dataset Table ids: " + ", ".join(duplicate_table_ids)
            )
        errors.extend(_relationship_errors(self.datasets, self.tables))
        if errors:
            raise ValueError("\n".join(_unique_messages(errors)))

    def find_dataset(self, dataset_id: str) -> schema.CuratedDataset:
        for dataset in self.datasets:
            if dataset.dataset_id == dataset_id:
                return dataset
        msg = f"Curated Dataset not found: {dataset_id}"
        raise ValueError(msg)

    def find_table(self, table_id: str) -> schema.DatasetTable:
        for table in self.tables:
            if table.table_id == table_id:
                return table
        msg = f"Dataset Table not found: {table_id}"
        raise ValueError(msg)

    def tables_for_dataset_id(self, dataset_id: str) -> tuple[schema.DatasetTable, ...]:
        dataset = self.find_dataset(dataset_id)
        return tuple(
            table
            for table in self.tables
            if table.table_id in dataset.tables and table.dataset_id == dataset_id
        )


def _duplicate_ids(ids: collections.abc.Iterable[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    duplicates: list[str] = []
    for item_id in ids:
        if item_id in seen and item_id not in duplicates:
            duplicates.append(item_id)
            continue
        seen.add(item_id)
    return tuple(duplicates)


def _relationship_errors(
    datasets: tuple[schema.CuratedDataset, ...],
    tables: tuple[schema.DatasetTable, ...],
) -> tuple[str, ...]:
    table_ids = {table.table_id for table in tables}
    tables_by_id = {table.table_id: table for table in tables}
    dataset_ids_by_table_id: dict[str, list[str]] = collections.defaultdict(list)
    errors: list[str] = []

    for dataset in datasets:
        unknown_table_ids = sorted(
            table_id for table_id in dataset.tables if table_id not in table_ids
        )
        if unknown_table_ids:
            errors.append(
                "Unknown Dataset Table refs for Curated Dataset "
                f"{dataset.dataset_id}: {', '.join(unknown_table_ids)}"
            )

        for table_id in dataset.tables:
            dataset_ids_by_table_id[table_id].append(dataset.dataset_id)
            table = tables_by_id.get(table_id)
            if table is None:
                continue
            if table.dataset_id != dataset.dataset_id:
                errors.append(
                    "Curated Dataset "
                    f"{dataset.dataset_id} lists Dataset Table {table_id}, "
                    f"but table.dataset_id is {table.dataset_id}"
                )

    duplicate_dataset_refs = sorted(
        table_id
        for table_id, dataset_ids in dataset_ids_by_table_id.items()
        if len(dataset_ids) > 1 and table_id in table_ids
    )
    if duplicate_dataset_refs:
        errors.append(
            "Dataset Table refs listed by multiple Curated Datasets: "
            + ", ".join(duplicate_dataset_refs)
        )

    orphan_table_ids = sorted(
        table.table_id
        for table in tables
        if table.table_id not in dataset_ids_by_table_id
    )
    if orphan_table_ids:
        errors.append(
            "Orphan Dataset Tables not listed by any Curated Dataset: "
            + ", ".join(orphan_table_ids)
        )

    return _unique_messages(errors)


def _unique_messages(messages: collections.abc.Iterable[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    unique_messages: list[str] = []
    for message in messages:
        if message in seen:
            continue
        seen.add(message)
        unique_messages.append(message)
    return tuple(unique_messages)

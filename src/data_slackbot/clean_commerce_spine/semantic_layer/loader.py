"""Semantic Layer YAML loader."""

from __future__ import annotations

import pathlib

import yaml

import data_slackbot.clean_commerce_spine.semantic_layer.schema as schema

DEFAULT_SEMANTIC_LAYER_PATH = pathlib.Path("semantic_layer")


def load_semantic_layer(
    path: pathlib.Path = DEFAULT_SEMANTIC_LAYER_PATH,
) -> schema.SemanticLayer:
    """Load Semantic Layer dataset and table definitions from YAML files."""
    datasets_path = path / "datasets"
    tables_path = path / "tables"
    datasets = tuple(
        _load_dataset(dataset_path)
        for dataset_path in sorted(datasets_path.glob("*.yaml"))
    )
    tables = tuple(
        _load_table(table_path) for table_path in sorted(tables_path.glob("*.yaml"))
    )

    if not datasets:
        msg = f"No Curated Dataset YAML files found in {datasets_path}"
        raise ValueError(msg)
    if not tables:
        msg = f"No Dataset Table YAML files found in {tables_path}"
        raise ValueError(msg)

    return schema.SemanticLayer(datasets=datasets, tables=tables)


def find_dataset(
    dataset_id: str,
    semantic_layer: schema.SemanticLayer,
) -> schema.CuratedDataset:
    """Find a Curated Dataset by id."""
    for dataset in semantic_layer.datasets:
        if dataset.dataset_id == dataset_id:
            return dataset

    msg = f"Curated Dataset not found: {dataset_id}"
    raise ValueError(msg)


def find_table(
    table_id: str,
    semantic_layer: schema.SemanticLayer,
) -> schema.DatasetTable:
    """Find a Dataset Table by id."""
    for table in semantic_layer.tables:
        if table.table_id == table_id:
            return table

    msg = f"Dataset Table not found: {table_id}"
    raise ValueError(msg)


def tables_for_dataset(
    dataset: schema.CuratedDataset,
    semantic_layer: schema.SemanticLayer,
) -> tuple[schema.DatasetTable, ...]:
    """Return Dataset Tables listed by a Curated Dataset."""
    return tuple(
        table
        for table in semantic_layer.tables
        if table.table_id in dataset.tables and table.dataset_id == dataset.dataset_id
    )


def _load_dataset(path: pathlib.Path) -> schema.CuratedDataset:
    return schema.CuratedDataset.model_validate(_load_yaml(path))


def _load_table(path: pathlib.Path) -> schema.DatasetTable:
    return schema.DatasetTable.model_validate(_load_yaml(path))


def _load_yaml(path: pathlib.Path) -> object:
    return yaml.safe_load(path.read_text(encoding="utf-8"))

"""Semantic Layer YAML loader."""

from __future__ import annotations

import collections.abc
import datetime
import pathlib
import typing

import yaml

from data_slackbot.clean_commerce_spine import contracts

DEFAULT_SEMANTIC_LAYER_PATH = pathlib.Path("semantic_layer")
YamlMapping: typing.TypeAlias = collections.abc.Mapping[str, object]


def load_semantic_layer(
    path: pathlib.Path = DEFAULT_SEMANTIC_LAYER_PATH,
) -> contracts.SemanticLayer:
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

    return contracts.SemanticLayer(datasets=datasets, tables=tables)


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


def find_table(
    table_id: str,
    semantic_layer: contracts.SemanticLayer,
) -> contracts.DatasetTable:
    """Find a Dataset Table by id."""
    for table in semantic_layer.tables:
        if table.table_id == table_id:
            return table

    msg = f"Dataset Table not found: {table_id}"
    raise ValueError(msg)


def tables_for_dataset(
    dataset: contracts.CuratedDataset,
    semantic_layer: contracts.SemanticLayer,
) -> tuple[contracts.DatasetTable, ...]:
    """Return Dataset Tables listed by a Curated Dataset."""
    return tuple(
        table
        for table in semantic_layer.tables
        if table.table_id in dataset.tables and table.dataset_id == dataset.dataset_id
    )


def find_table_for_question_frame(
    dataset: contracts.CuratedDataset,
    question_frame: contracts.QuestionFrame,
    semantic_layer: contracts.SemanticLayer,
) -> tuple[contracts.DatasetTable, contracts.Metric, contracts.Dimension]:
    """Find the table-level metric and dimension for a Question Frame."""
    for table in tables_for_dataset(dataset, semantic_layer):
        metric = _find_metric(question_frame.metric, table)
        dimension = _find_dimension(question_frame.dimension, table)
        if metric is not None and dimension is not None:
            return table, metric, dimension

    msg = (
        f"No Dataset Table in {dataset.dataset_id} supports "
        f"{question_frame.metric} by {question_frame.dimension}."
    )
    raise ValueError(msg)


def _load_dataset(path: pathlib.Path) -> contracts.CuratedDataset:
    data = _load_yaml_mapping(path)
    freshness = _required_mapping(data, "freshness")
    return contracts.CuratedDataset(
        dataset_id=_required_str(data, "id"),
        name=_required_str(data, "name"),
        tables=_required_str_tuple(data, "tables"),
        information_types=_required_str_tuple(data, "information_types"),
        freshness=contracts.Freshness(
            as_of=_required_date(freshness, "as_of"),
            description=_required_str(freshness, "description"),
        ),
        example_questions=_required_str_tuple(data, "example_questions"),
    )


def _load_table(path: pathlib.Path) -> contracts.DatasetTable:
    data = _load_yaml_mapping(path)
    return contracts.DatasetTable(
        table_id=_required_str(data, "id"),
        dataset_id=_required_str(data, "dataset_id"),
        description=_required_str(data, "description"),
        date_column=_required_str(data, "date_column"),
        columns=tuple(
            contracts.TableColumn(
                column_id=_required_str(column, "id"),
                data_type=_required_str(column, "type"),
                semantic_role=_optional_str(column, "semantic_role"),
            )
            for column in _required_mapping_tuple(data, "columns")
        ),
        metrics=tuple(
            contracts.Metric(
                metric_id=_required_str(metric, "id"),
                label=_required_str(metric, "label"),
                expression=_required_str(metric, "expression"),
            )
            for metric in _required_mapping_tuple(data, "metrics")
        ),
        dimensions=tuple(
            contracts.Dimension(
                dimension_id=_required_str(dimension, "id"),
                label=_required_str(dimension, "label"),
                column=_required_str(dimension, "column"),
            )
            for dimension in _required_mapping_tuple(data, "dimensions")
        ),
    )


def _find_metric(
    metric_label: str,
    table: contracts.DatasetTable,
) -> contracts.Metric | None:
    return next(
        (metric for metric in table.metrics if metric.label == metric_label),
        None,
    )


def _find_dimension(
    dimension_label: str,
    table: contracts.DatasetTable,
) -> contracts.Dimension | None:
    return next(
        (
            dimension
            for dimension in table.dimensions
            if dimension.label == dimension_label
        ),
        None,
    )


def _load_yaml_mapping(path: pathlib.Path) -> YamlMapping:
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, collections.abc.Mapping):
        msg = f"Expected YAML mapping in {path}"
        raise ValueError(msg)
    return typing.cast(YamlMapping, loaded)


def _required_mapping(data: YamlMapping, key: str) -> YamlMapping:
    value = data.get(key)
    if not isinstance(value, collections.abc.Mapping):
        msg = f"Expected mapping for {key}"
        raise ValueError(msg)
    return typing.cast(YamlMapping, value)


def _required_mapping_tuple(data: YamlMapping, key: str) -> tuple[YamlMapping, ...]:
    values = _required_sequence(data, key)
    mappings: list[YamlMapping] = []
    for value in values:
        if not isinstance(value, collections.abc.Mapping):
            msg = f"Expected mappings in {key}"
            raise ValueError(msg)
        mappings.append(typing.cast(YamlMapping, value))
    return tuple(mappings)


def _required_str_tuple(data: YamlMapping, key: str) -> tuple[str, ...]:
    values = _required_sequence(data, key)
    if not all(isinstance(value, str) for value in values):
        msg = f"Expected strings in {key}"
        raise ValueError(msg)
    return tuple(typing.cast(collections.abc.Sequence[str], values))


def _required_sequence(data: YamlMapping, key: str) -> collections.abc.Sequence[object]:
    value = data.get(key)
    if not isinstance(value, collections.abc.Sequence) or isinstance(value, str):
        msg = f"Expected sequence for {key}"
        raise ValueError(msg)
    return typing.cast(collections.abc.Sequence[object], value)


def _required_str(data: YamlMapping, key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str):
        msg = f"Expected string for {key}"
        raise ValueError(msg)
    return value


def _optional_str(data: YamlMapping, key: str) -> str | None:
    value = data.get(key)
    if value is None or isinstance(value, str):
        return value
    msg = f"Expected optional string for {key}"
    raise ValueError(msg)


def _required_date(data: YamlMapping, key: str) -> datetime.date:
    value = _required_str(data, key)
    return datetime.date.fromisoformat(value)

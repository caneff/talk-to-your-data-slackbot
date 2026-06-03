"""Business-facing Semantic Layer context for Question Interpreter providers."""

from __future__ import annotations

import datetime
import typing

import data_assistant.semantic_layer.catalog as semantic_layer_catalog
import data_assistant.semantic_layer.schema as schema

_SUPPORTED_PROVIDER_INTENTS = frozenset({"summarize"})


def build_semantic_layer_context(
    semantic_layer: semantic_layer_catalog.SemanticLayerCatalog,
) -> dict[str, object]:
    """Collect business-facing context from the Semantic Layer only.

    Build just what the Question Interpreter should need: labels, examples, and
    supported intents, without IDs, table names, SQL, columns, or access internals.
    """
    datasets: list[dict[str, object]] = []
    for dataset in semantic_layer.datasets:
        dataset_tables = semantic_layer.tables_for_dataset_id(dataset.dataset_id)
        datasets.append(
            {
                "name": dataset.name,
                "information_types": list(dataset.information_types),
                "example_questions": list(dataset.example_questions),
                "available_metric_labels": sorted(
                    {
                        metric.label
                        for table in dataset_tables
                        for metric in table.metrics
                    }
                ),
                "metric_contexts": sorted(
                    [
                        {
                            "metric_label": metric.label,
                            "available_fields": _field_contexts(table.fields),
                            "available_field_labels": sorted(
                                field.label for field in table.fields
                            ),
                        }
                        for table in dataset_tables
                        for metric in table.metrics
                    ],
                    key=lambda metric_context: typing.cast(
                        str,
                        metric_context["metric_label"],
                    ),
                ),
            }
        )

    context: dict[str, object] = {
        "datasets": datasets,
        "all_metric_labels": sorted(set(metric_labels(semantic_layer))),
        "supported_intents": sorted(_SUPPORTED_PROVIDER_INTENTS),
    }
    as_of_date = _as_of_date(semantic_layer)
    if as_of_date is not None:
        context["as_of_date"] = as_of_date.isoformat()
    return context


def _as_of_date(
    semantic_layer: semantic_layer_catalog.SemanticLayerCatalog,
) -> datetime.date | None:
    for dataset in semantic_layer.datasets:
        if dataset.as_of_date is not None:
            return dataset.as_of_date
    return None


def metric_labels(
    semantic_layer: semantic_layer_catalog.SemanticLayerCatalog,
) -> tuple[str, ...]:
    return tuple(
        metric.label for table in semantic_layer.tables for metric in table.metrics
    )


def field_labels(
    semantic_layer: semantic_layer_catalog.SemanticLayerCatalog,
) -> tuple[str, ...]:
    return tuple(
        field.label for table in semantic_layer.tables for field in table.fields
    )


def _field_contexts(
    fields: tuple[schema.SemanticField, ...],
) -> list[dict[str, object]]:
    return sorted(
        [
            {
                "label": field.label,
                "data_type": field.data_type,
                "operations": sorted(operation.value for operation in field.operations),
            }
            for field in fields
        ],
        key=lambda field_context: typing.cast(str, field_context["label"]),
    )

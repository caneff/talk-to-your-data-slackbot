import datetime

import pytest

import data_assistant.semantic_layer.schema as schema


def test_curated_dataset_parses_as_of_date_scalar() -> None:
    dataset = schema.CuratedDataset.model_validate(
        {
            "dataset_id": "retail_ops",
            "name": "Retail Operations",
            "tables": ("orders",),
            "information_types": ("revenue",),
            "example_questions": ("What was total revenue?",),
            "as_of_date": "2026-06-30",
        }
    )
    assert dataset.as_of_date == datetime.date(2026, 6, 30)


def test_curated_dataset_as_of_date_defaults_to_none_when_omitted() -> None:
    dataset = schema.CuratedDataset.model_validate(
        {
            "dataset_id": "retail_ops",
            "name": "Retail Operations",
            "tables": ("orders",),
            "information_types": ("revenue",),
            "example_questions": ("What was total revenue?",),
        }
    )
    assert dataset.as_of_date is None


def test_curated_dataset_rejects_malformed_as_of_date() -> None:
    with pytest.raises(Exception, match="as_of_date"):
        schema.CuratedDataset.model_validate(
            {
                "dataset_id": "retail_ops",
                "name": "Retail Operations",
                "tables": ("orders",),
                "information_types": ("revenue",),
                "example_questions": ("What was total revenue?",),
                "as_of_date": "not-a-date",
            }
        )


def test_data_type_has_exactly_one_member_per_logical_type() -> None:
    assert set(schema.DataType) == {
        schema.DataType.DATE,
        schema.DataType.DECIMAL,
        schema.DataType.STRING,
    }


def test_data_type_drops_collapsed_synonyms() -> None:
    member_names = {member.name for member in schema.DataType}
    assert "NUMBER" not in member_names
    assert "VARCHAR" not in member_names


def test_metric_requires_kind() -> None:
    with pytest.raises(Exception, match="kind"):
        schema.Metric.model_validate(
            {
                "metric_id": "total_revenue",
                "label": "total revenue",
                "expression": "sum(revenue)",
                "source_column": "revenue",
            }
        )


def test_metric_aliases_default_to_empty_tuple() -> None:
    metric = schema.Metric.model_validate(
        {
            "metric_id": "total_revenue",
            "label": "total revenue",
            "expression": "sum(revenue)",
            "source_column": "revenue",
            "kind": "money",
        }
    )

    assert metric.aliases == ()

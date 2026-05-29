import datetime
import typing

import data_assistant.question_interpreter as question_interpreter
import data_assistant.semantic_layer.schema as schema


def test_semantic_layer_context_exposes_business_labels_not_storage_details() -> None:
    semantic_layer = schema.SemanticLayer(
        datasets=(
            schema.CuratedDataset(
                dataset_id="internal_commerce",
                name="Commerce Revenue",
                tables=("orders_internal",),
                information_types=("revenue", "regional performance"),
                freshness=schema.Freshness(
                    as_of=datetime.date(2026, 1, 31),
                    description="Loaded nightly.",
                ),
                example_questions=(
                    "What was total revenue by customer region in January 2026?",
                ),
                dataset_access=schema.DatasetAccess(
                    allowed_identity_ids=("finance-team",),
                ),
            ),
        ),
        tables=(
            schema.DatasetTable(
                table_id="orders_internal",
                dataset_id="internal_commerce",
                description="Internal orders table.",
                date_column="order_date",
                columns=(
                    schema.TableColumn(column_id="order_date", data_type="date"),
                    schema.TableColumn(column_id="net_revenue", data_type="decimal"),
                    schema.TableColumn(column_id="region_code", data_type="varchar"),
                ),
                metrics=(
                    schema.Metric(
                        metric_id="metric_total_revenue",
                        label="total revenue",
                        expression="sum(net_revenue)",
                        source_column="net_revenue",
                    ),
                ),
                dimensions=(
                    schema.Dimension(
                        dimension_id="customer_region",
                        label="customer region",
                        column="region_code",
                    ),
                ),
            ),
        ),
    )

    semantic_layer_context = question_interpreter.build_semantic_layer_context(
        semantic_layer
    )
    dataset_context = _single_dataset_context(semantic_layer_context)
    metric_labels = typing.cast(list[str], semantic_layer_context["all_metric_labels"])
    dimension_labels = typing.cast(
        list[str],
        semantic_layer_context["all_dimension_labels"],
    )
    example_questions = typing.cast(list[str], dataset_context["example_questions"])

    assert dataset_context["name"] == "Commerce Revenue"
    assert "total revenue" in metric_labels
    assert "customer region" in dimension_labels
    assert "What was total revenue by customer region in January 2026?" in (
        example_questions
    )

    context_text = repr(semantic_layer_context)
    for storage_detail in (
        "orders_internal",
        "net_revenue",
        "finance-team",
    ):
        assert storage_detail not in context_text


def _single_dataset_context(
    semantic_layer_context: dict[str, object],
) -> dict[str, object]:
    datasets = typing.cast(
        list[dict[str, object]],
        semantic_layer_context["datasets"],
    )
    assert len(datasets) == 1
    return datasets[0]

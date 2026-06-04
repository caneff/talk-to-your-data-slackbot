import datetime
import json
import typing

import data_assistant.question_interpreter as question_interpreter
import data_assistant.semantic_layer.catalog as semantic_layer_catalog
import data_assistant.semantic_layer.schema as schema
import data_assistant.semantic_layer.testing_support as testing_support


def test_semantic_layer_context_emits_as_of_date_as_json_serializable_iso_string() -> (
    None
):
    semantic_layer = testing_support.semantic_layer_with_table()
    semantic_layer = semantic_layer_catalog.SemanticLayerCatalog(
        datasets=(
            semantic_layer.datasets[0].model_copy(
                update={"as_of_date": datetime.date(2026, 6, 30)},
            ),
        ),
        tables=semantic_layer.tables,
    )

    context = question_interpreter.build_semantic_layer_context(semantic_layer)

    assert context["as_of_date"] == "2026-06-30"
    json.dumps(context)


def test_semantic_layer_context_omits_as_of_date_when_dataset_has_none() -> None:
    semantic_layer = testing_support.semantic_layer_with_table()

    context = question_interpreter.build_semantic_layer_context(semantic_layer)

    assert "as_of_date" not in context


def test_semantic_layer_context_exposes_business_labels_not_storage_details() -> None:
    semantic_layer = semantic_layer_catalog.SemanticLayerCatalog(
        datasets=(
            schema.CuratedDataset(
                dataset_id="internal_retail",
                name="Retail Operations",
                tables=("orders_internal", "customers_internal"),
                information_types=("revenue", "regional performance"),
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
                dataset_id="internal_retail",
                description="Internal orders table.",
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
                        kind=schema.MetricKind.MONEY,
                    ),
                ),
                fields=(
                    schema.SemanticField(
                        field_id="customer_region",
                        label="customer region",
                        source_column="region_code",
                        data_type=schema.DataType.STRING,
                        operations=(schema.FieldOperation.GROUP_BY,),
                    ),
                ),
            ),
            schema.DatasetTable(
                table_id="customers_internal",
                dataset_id="internal_retail",
                description="Internal customers table.",
                columns=(
                    schema.TableColumn(column_id="created_date", data_type="date"),
                    schema.TableColumn(column_id="customer_id", data_type="varchar"),
                    schema.TableColumn(column_id="region_code", data_type="varchar"),
                ),
                metrics=(
                    schema.Metric(
                        metric_id="metric_customer_count",
                        label="customer count",
                        expression="count(customer_id)",
                        source_column="customer_id",
                        kind=schema.MetricKind.COUNT,
                    ),
                ),
                fields=(
                    schema.SemanticField(
                        field_id="created_date",
                        label="created date",
                        source_column="created_date",
                        data_type=schema.DataType.DATE,
                        operations=(schema.FieldOperation.RANGE_FILTER,),
                    ),
                    schema.SemanticField(
                        field_id="customer_region",
                        label="customer region",
                        source_column="region_code",
                        data_type=schema.DataType.STRING,
                        operations=(schema.FieldOperation.GROUP_BY,),
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
    example_questions = typing.cast(list[str], dataset_context["example_questions"])
    metric_contexts = typing.cast(
        list[dict[str, object]],
        dataset_context["metric_contexts"],
    )

    assert dataset_context["name"] == "Retail Operations"
    assert "total revenue" in metric_labels
    assert "customer count" in metric_labels
    assert "What was total revenue by customer region in January 2026?" in (
        example_questions
    )
    assert {
        metric_context["metric_label"]: metric_context["available_field_labels"]
        for metric_context in metric_contexts
    } == {
        "customer count": ["created date", "customer region"],
        "total revenue": ["customer region"],
    }

    context_text = repr(semantic_layer_context)
    for storage_detail in (
        "orders_internal",
        "customers_internal",
        "net_revenue",
        "created_date",
        "customer_id",
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

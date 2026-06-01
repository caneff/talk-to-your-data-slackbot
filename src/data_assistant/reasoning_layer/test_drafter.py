import datetime

import pandas as pd

import data_assistant.reasoning_layer as reasoning_layer
import data_assistant.semantic_layer.schema as schema
import data_assistant.workflow.contracts as contracts


def _commerce_revenue_dataset() -> schema.CuratedDataset:
    return schema.CuratedDataset(
        dataset_id="commerce",
        name="Commerce",
        tables=("orders",),
        information_types=("revenue",),
        freshness=schema.Freshness(
            as_of=datetime.date(2026, 1, 31),
            description="Commerce order data refreshed through 2026-01-31.",
        ),
        example_questions=(),
    )


def _orders_table() -> schema.DatasetTable:
    return schema.DatasetTable(
        table_id="orders",
        dataset_id="commerce",
        description="Orders by date and region.",
        columns=(
            schema.TableColumn(column_id="order_date", data_type="date"),
            schema.TableColumn(column_id="region", data_type="varchar"),
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
            schema.SemanticField(
                field_id="order_date",
                label="order date",
                source_column="order_date",
                data_type=schema.DataType.DATE,
                operations=(schema.FieldOperation.RANGE_FILTER,),
            ),
        ),
    )


def _prepared_revenue_by_region() -> contracts.PreparedData:
    dataset = _commerce_revenue_dataset()
    table = _orders_table()
    return contracts.PreparedData(
        request=contracts.DataRequest(
            dataset=dataset,
            table=table,
            metric=table.metrics[0],
            group_by_fields=(table.fields[0],),
            filter_operations=(
                contracts.ResolvedSemanticFieldOperation(
                    operation=schema.FieldOperation.RANGE_FILTER,
                    field=table.fields[1],
                    lower=datetime.date(2026, 1, 1),
                    upper=datetime.date(2026, 1, 31),
                ),
            ),
            output_shape="grouped_metric",
            result_limit=10,
        ),
        data=pd.DataFrame(
            {
                "dimension_value": ("West", "North", "East", "South", "Unknown"),
                "metric_value": (1600.0, 1500.0, 950.0, 850.0, 250.0),
            }
        ),
        quality_notes=(
            "1 row excluded because revenue was missing.",
            "1 row grouped under Unknown because region was missing.",
        ),
    )


def test_reasoning_layer_produces_answer_draft_from_prepared_data() -> None:
    prepared_data = _prepared_revenue_by_region()

    answer_draft = reasoning_layer.draft_answer(prepared_data)

    assert answer_draft.summary == (
        "Total revenue in 2026-01-01 through 2026-01-31 was $5,150.00, "
        "grouped across 5 regions."
    )
    assert answer_draft.key_data is prepared_data.data
    assert answer_draft.datasets_used == ("Commerce",)
    assert answer_draft.dataset_tables_used == ("orders",)
    assert answer_draft.metric_kind == schema.MetricKind.MONEY
    assert answer_draft.time_range == "2026-01-01 through 2026-01-31"
    assert answer_draft.filters == ("order date >= 2026-01-01 and <= 2026-01-31",)
    assert answer_draft.freshness == (
        "Commerce order data refreshed through 2026-01-31."
    )
    assert answer_draft.caveats == (
        "1 row excluded because revenue was missing.",
        "1 row grouped under Unknown because region was missing.",
    )


def test_reasoning_layer_formats_count_summary_and_carries_metric_kind() -> None:
    dataset = schema.CuratedDataset(
        dataset_id="commerce",
        name="Commerce Customers",
        tables=("customers",),
        information_types=("customers",),
        freshness=schema.Freshness(
            as_of=datetime.date(2026, 1, 31),
            description="Commerce customer data refreshed through 2026-01-31.",
        ),
        example_questions=(),
    )
    table = schema.DatasetTable(
        table_id="customers",
        dataset_id="commerce",
        description="Customers by region.",
        columns=(
            schema.TableColumn(column_id="created_date", data_type="date"),
            schema.TableColumn(column_id="customer_region", data_type="varchar"),
            schema.TableColumn(column_id="customer_id", data_type="string"),
        ),
        metrics=(
            schema.Metric(
                metric_id="customer_count",
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
        ),
    )
    prepared_data = contracts.PreparedData(
        request=contracts.DataRequest(
            dataset=dataset,
            table=table,
            metric=table.metrics[0],
            group_by_fields=(),
            filter_operations=(
                contracts.ResolvedSemanticFieldOperation(
                    operation=schema.FieldOperation.RANGE_FILTER,
                    field=table.fields[0],
                    lower=datetime.date(2026, 1, 1),
                    upper=datetime.date(2026, 1, 31),
                ),
            ),
            output_shape="scalar_metric",
            result_limit=1,
        ),
        data=pd.DataFrame({"metric_value": (1234,)}),
        quality_notes=(),
    )

    answer_draft = reasoning_layer.draft_answer(prepared_data)

    assert answer_draft.summary == (
        "Customer count in 2026-01-01 through 2026-01-31 was 1,234."
    )
    assert answer_draft.metric_kind == schema.MetricKind.COUNT


def test_reasoning_layer_labels_all_time_when_no_date_filter_exists() -> None:
    prepared_data = _prepared_revenue_by_region()
    prepared_data = contracts.PreparedData(
        request=contracts.DataRequest(
            dataset=prepared_data.request.dataset,
            table=prepared_data.request.table,
            metric=prepared_data.request.metric,
            group_by_fields=prepared_data.request.group_by_fields,
            filter_operations=(),
            output_shape=prepared_data.request.output_shape,
            result_limit=prepared_data.request.result_limit,
        ),
        data=prepared_data.data,
        quality_notes=prepared_data.quality_notes,
    )

    answer_draft = reasoning_layer.draft_answer(prepared_data)

    assert answer_draft.summary == (
        "Total revenue in all available data was $5,150.00, grouped across 5 regions."
    )
    assert answer_draft.time_range == "all available data"
    assert answer_draft.filters == ()

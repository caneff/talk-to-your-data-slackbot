import datetime

import pandas as pd

import data_assistant.reasoning_layer as reasoning_layer
import data_assistant.semantic_layer.schema as schema
import data_assistant.workflow.contracts as contracts


def _commerce_revenue_dataset() -> schema.CuratedDataset:
    return schema.CuratedDataset(
        dataset_id="commerce",
        name="Commerce Revenue",
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
        date_column="order_date",
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
            ),
        ),
        dimensions=(
            schema.Dimension(
                dimension_id="region",
                label="region",
                column="region",
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
            dimension=table.dimensions[0],
            time_range=contracts.TimeRange(
                label="January 2026",
                start_date=datetime.date(2026, 1, 1),
                end_date=datetime.date(2026, 1, 31),
            ),
            filters=(),
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
        "Total revenue in January 2026 was $5,150.00, grouped across 5 regions."
    )
    assert answer_draft.key_data is prepared_data.data
    assert answer_draft.datasets_used == ("Commerce Revenue",)
    assert answer_draft.dataset_tables_used == ("orders",)
    assert answer_draft.time_range == "January 2026"
    assert answer_draft.filters == ()
    assert answer_draft.freshness == (
        "Commerce order data refreshed through 2026-01-31."
    )
    assert answer_draft.caveats == (
        "1 row excluded because revenue was missing.",
        "1 row grouped under Unknown because region was missing.",
    )

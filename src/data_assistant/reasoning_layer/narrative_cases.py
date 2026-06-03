"""Shared Reasoning Layer narrative fixtures and grounding-property cases.

Single source of truth for the ``PreparedData`` builders used by the drafter
tests and the manual live eval suite, plus the per-case grounding expectations
the live eval asserts. Keeping the fixtures here prevents drift between the
deterministic tests and the live eval cases.
"""

from __future__ import annotations

import dataclasses
import datetime

import pandas as pd

import data_assistant.semantic_layer.schema as schema
import data_assistant.workflow.contracts as contracts


@dataclasses.dataclass(frozen=True)
class GroundingExpectation:
    """Per-case grounding properties the live eval asserts for one fixture."""

    required_slots: tuple[str, ...] = ()


@dataclasses.dataclass(frozen=True)
class SharedNarrativeCase:
    """One canonical Prepared Data fixture and its grounding expectation."""

    name: str
    prepared_data: contracts.PreparedData
    expectation: GroundingExpectation
    enabled: bool = True


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


def prepared_revenue_by_region(*, all_time: bool = False) -> contracts.PreparedData:
    """Grouped revenue-by-region fixture (West/North/East/South/Unknown).

    With ``all_time=True`` the date range filter is dropped (everything else
    identical), exercising the "all available data" labelling path.
    """
    dataset = _commerce_revenue_dataset()
    table = _orders_table()
    field_filters: tuple[contracts.FieldFilter[schema.SemanticField], ...] = (
        ()
        if all_time
        else (
            contracts.RangeFilter(
                field=table.fields[1],
                lower=datetime.date(2026, 1, 1),
                upper=datetime.date(2026, 1, 31),
            ),
        )
    )
    return contracts.PreparedData(
        request=contracts.DataRequest(
            dataset=dataset,
            table=table,
            metric=table.metrics[0],
            group_by_field=table.fields[0],
            field_filters=field_filters,
            output_shape="grouped_metric",
            result_limit=10,
        ),
        # Already ordered metric_value desc, dimension_value asc.
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


def prepared_empty_revenue_by_region() -> contracts.PreparedData:
    """Grouped revenue-by-region fixture where filters match no rows."""
    prepared_data = prepared_revenue_by_region()
    request = dataclasses.replace(
        prepared_data.request,
        field_filters=(
            contracts.RangeFilter(
                field=prepared_data.request.field_filters[0].field,
                lower=datetime.date(2025, 10, 1),
                upper=datetime.date(2025, 12, 31),
            ),
        ),
    )
    return dataclasses.replace(
        prepared_data,
        request=request,
        data=pd.DataFrame(
            {
                "dimension_value": pd.Series(dtype="object"),
                "metric_value": pd.Series(dtype="float64"),
            }
        ),
        quality_notes=("No rows matched the request filters.",),
    )


def prepared_customer_count() -> contracts.PreparedData:
    """Scalar customer-count fixture with no group-by ranking."""
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
    return contracts.PreparedData(
        request=contracts.DataRequest(
            dataset=dataset,
            table=table,
            metric=table.metrics[0],
            group_by_field=None,
            field_filters=(
                contracts.RangeFilter(
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


SHARED_NARRATIVE_CASES: tuple[SharedNarrativeCase, ...] = (
    SharedNarrativeCase(
        name="grouped_revenue_by_region",
        prepared_data=prepared_revenue_by_region(),
        # The leader clause is stylistic; the safety-only bar (grounded +
        # fillable + headline {metric_total} survives) carries the floor.
        expectation=GroundingExpectation(required_slots=()),
    ),
    SharedNarrativeCase(
        name="scalar_customer_count",
        prepared_data=prepared_customer_count(),
        expectation=GroundingExpectation(
            required_slots=("{metric_total}",),
        ),
    ),
    SharedNarrativeCase(
        name="all_time_revenue_by_region",
        prepared_data=prepared_revenue_by_region(all_time=True),
        expectation=GroundingExpectation(required_slots=()),
    ),
)

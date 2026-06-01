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
    expect_grounded: bool = True
    expect_fillable: bool = True
    expect_values_present: bool = True
    allow_degrade: bool = False


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


def prepared_revenue_by_region() -> contracts.PreparedData:
    """Grouped revenue-by-region fixture (West/North/East/South/Unknown)."""
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


def prepared_all_time_revenue_by_region() -> contracts.PreparedData:
    """Grouped revenue-by-region fixture with no date filter (all available)."""
    grouped = prepared_revenue_by_region()
    return contracts.PreparedData(
        request=contracts.DataRequest(
            dataset=grouped.request.dataset,
            table=grouped.request.table,
            metric=grouped.request.metric,
            group_by_fields=grouped.request.group_by_fields,
            filter_operations=(),
            output_shape=grouped.request.output_shape,
            result_limit=grouped.request.result_limit,
        ),
        data=grouped.data,
        quality_notes=grouped.quality_notes,
    )


SHARED_NARRATIVE_CASES: tuple[SharedNarrativeCase, ...] = (
    SharedNarrativeCase(
        name="grouped_revenue_by_region",
        prepared_data=prepared_revenue_by_region(),
        expectation=GroundingExpectation(
            required_slots=("{top_dimension}",),
        ),
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
        prepared_data=prepared_all_time_revenue_by_region(),
        expectation=GroundingExpectation(
            required_slots=("{top_dimension}",),
        ),
    ),
    # Adversarial: a ranked-dimension shape structurally tempts an invented
    # comparison ("by what percent..."). The reasoning model never sees the
    # user question, only the figure-free result_shape, so the temptation is
    # purely structural. Safe property: grounded+filled OR a visible degrade,
    # never a fabricated figure.
    SharedNarrativeCase(
        name="adversarial_ranked_dimensions",
        prepared_data=prepared_revenue_by_region(),
        expectation=GroundingExpectation(
            required_slots=(),
            allow_degrade=True,
        ),
    ),
)

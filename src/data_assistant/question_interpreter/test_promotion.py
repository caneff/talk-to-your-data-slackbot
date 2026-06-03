"""Deterministic promotion regression tests for metric-qualifier handling.

These lock the ADR-0017 precedence both ways, independent of the LLM:
an exact qualified label (e.g. "total net revenue") must promote, while a
reported `metric_ambiguity` with no reflecting label must Non-Answer.
"""

from __future__ import annotations

import datetime

import data_assistant.question_interpreter as question_interpreter
import data_assistant.semantic_layer.catalog as semantic_layer_catalog
import data_assistant.semantic_layer.schema as schema
import data_assistant.semantic_layer.testing_support as semantic_layer_testing
import data_assistant.workflow.contracts as contracts


def _retail_style_semantic_layer() -> semantic_layer_catalog.SemanticLayerCatalog:
    """Build a layer exposing both 'total revenue' and 'total net revenue'."""
    return semantic_layer_testing.semantic_layer_with_table(
        columns={
            "order_date": "date",
            "region": "varchar",
            "revenue": "decimal",
            "net_revenue": "decimal",
        },
        metrics=(
            schema.Metric(
                metric_id="total_revenue",
                label="total revenue",
                expression="sum(revenue)",
                source_column="revenue",
                kind=schema.MetricKind.MONEY,
            ),
            schema.Metric(
                metric_id="total_net_revenue",
                label="total net revenue",
                expression="sum(net_revenue)",
                source_column="net_revenue",
                kind=schema.MetricKind.MONEY,
            ),
        ),
    )


class _StaticProvider:
    """Return a fixed proposal without calling an LLM."""

    def __init__(
        self,
        proposal: question_interpreter.QuestionFrameProposal,
    ) -> None:
        self._proposal = proposal

    def propose_question_frame(
        self,
        *,
        question: str,
        semantic_layer_context: dict[str, object],
    ) -> question_interpreter.QuestionFrameProposal:
        del question, semantic_layer_context
        return self._proposal


def test_exact_net_revenue_label_promotes_to_question_frame() -> None:
    proposal = question_interpreter.QuestionFrameProposal(
        intent="summarize",
        metric="total net revenue",
        metric_ambiguity=None,
        field_operations=(
            question_interpreter.RangeFilterOperationProposal(
                operation="range_filter",
                field="order date",
                lower="2026-01-01",
                upper="2026-01-31",
            ),
        ),
    )

    result = question_interpreter.interpret_question(
        question="What was total net revenue in January 2026?",
        semantic_layer=_retail_style_semantic_layer(),
        provider=_StaticProvider(proposal),
    )

    assert isinstance(result, contracts.Success)
    assert result.value.metric == "total net revenue"
    assert result.value.group_by_field is None
    assert result.value.field_filters == (
        contracts.RangeFilter(
            field="order date",
            lower=datetime.date(2026, 1, 1),
            upper=datetime.date(2026, 1, 31),
        ),
    )


def test_unreflected_metric_ambiguity_still_non_answers() -> None:
    proposal = question_interpreter.QuestionFrameProposal(
        intent="summarize",
        metric=None,
        metric_ambiguity="recurring revenue",
        field_operations=(
            question_interpreter.RangeFilterOperationProposal(
                operation="range_filter",
                field="order date",
                lower="2026-01-01",
                upper="2026-01-31",
            ),
        ),
    )

    result = question_interpreter.interpret_question(
        question="What was total recurring revenue in January 2026?",
        semantic_layer=_retail_style_semantic_layer(),
        provider=_StaticProvider(proposal),
    )

    assert isinstance(result, contracts.NonAnswer)
    assert result.reason_code == contracts.NonAnswerReasonCode.AMBIGUOUS_METRIC

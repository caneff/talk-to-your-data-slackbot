"""Deterministic Provider Proposal Validation tests for metric qualifiers.

These lock the ADR-0017 precedence both ways, independent of the LLM:
an exact qualified label (e.g. "total net revenue") must validate, while a
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
    """Build a layer exposing qualified revenue labels and a non-qualifier alias."""
    return semantic_layer_testing.semantic_layer_with_table(
        columns={
            "order_id": "varchar",
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
            schema.Metric(
                metric_id="order_count",
                label="order count",
                aliases=("order volume",),
                expression="count(order_id)",
                source_column="order_id",
                kind=schema.MetricKind.COUNT,
            ),
        ),
    )


class _StaticProvider:
    """Return a fixed proposal without calling an LLM."""

    def __init__(
        self,
        proposal: question_interpreter.ProviderProposal,
    ) -> None:
        self._proposal = proposal

    def propose_question_frame(
        self,
        *,
        question: str,
        semantic_layer_context: dict[str, object],
    ) -> question_interpreter.ProviderProposal:
        del question, semantic_layer_context
        return self._proposal


class _RaisingProvider:
    def propose_question_frame(
        self,
        *,
        question: str,
        semantic_layer_context: dict[str, object],
    ) -> question_interpreter.ProviderProposal:
        del question, semantic_layer_context
        raise RuntimeError("boom")


def test_provider_exception_returns_provider_failure_non_answer() -> None:
    result = question_interpreter.interpret_question(
        question="What was total revenue in January 2026?",
        semantic_layer=_retail_style_semantic_layer(),
        provider=_RaisingProvider(),
    )

    assert isinstance(result, contracts.NonAnswer)
    assert result.reason_code == contracts.NonAnswerReasonCode.PROVIDER_FAILURE


def test_exact_net_revenue_label_validates_to_question_frame() -> None:
    proposal = question_interpreter.ProviderProposal(
        intent="summarize",
        metric="total net revenue",
        metric_ambiguity=None,
        field_operations=(
            question_interpreter.ProviderFieldOperation(
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


def test_metric_alias_question_wording_can_resolve_to_canonical_metric_label() -> None:
    proposal = question_interpreter.ProviderProposal(
        intent="summarize",
        metric="order count",
        metric_ambiguity=None,
        field_operations=(
            question_interpreter.ProviderFieldOperation(
                operation="range_filter",
                field="order date",
                lower="2026-01-01",
                upper="2026-01-31",
            ),
        ),
    )

    result = question_interpreter.interpret_question(
        question="What was order volume in January 2026?",
        semantic_layer=_retail_style_semantic_layer(),
        provider=_StaticProvider(proposal),
    )

    assert isinstance(result, contracts.Success)
    assert result.value.metric == "order count"


def test_metric_alias_label_is_not_trusted_as_canonical_metric_value() -> None:
    proposal = question_interpreter.ProviderProposal(
        intent="summarize",
        metric="order volume",
        metric_ambiguity=None,
        field_operations=(
            question_interpreter.ProviderFieldOperation(
                operation="range_filter",
                field="order date",
                lower="2026-01-01",
                upper="2026-01-31",
            ),
        ),
    )

    result = question_interpreter.interpret_question(
        question="What was order volume in January 2026?",
        semantic_layer=_retail_style_semantic_layer(),
        provider=_StaticProvider(proposal),
    )

    assert isinstance(result, contracts.NonAnswer)
    assert result.reason_code == contracts.NonAnswerReasonCode.UNKNOWN_SEMANTIC_LABEL


def test_unreflected_metric_ambiguity_still_non_answers() -> None:
    proposal = question_interpreter.ProviderProposal(
        intent="summarize",
        metric=None,
        metric_ambiguity="recurring revenue",
        field_operations=(
            question_interpreter.ProviderFieldOperation(
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


def test_unknown_metric_non_answers_via_unknown_semantic_label() -> None:
    """A self-reported named-but-unavailable metric Non-Answers (issue #196).

    Mirrors the metric_ambiguity self-report but routes to UNKNOWN_SEMANTIC_LABEL:
    the user named a metric we genuinely do not carry (an unsupported-label
    situation), distinct from the qualifier-ambiguity clarification.
    """
    proposal = question_interpreter.ProviderProposal(
        intent="summarize",
        metric=None,
        unknown_metric="return rate",
        field_operations=(
            question_interpreter.ProviderFieldOperation(
                operation="range_filter",
                field="order date",
                lower="2026-01-01",
                upper="2026-01-31",
            ),
        ),
    )

    result = question_interpreter.interpret_question(
        question="What's our return rate in January 2026?",
        semantic_layer=_retail_style_semantic_layer(),
        provider=_StaticProvider(proposal),
    )

    assert isinstance(result, contracts.NonAnswer)
    assert result.reason_code == contracts.NonAnswerReasonCode.UNKNOWN_SEMANTIC_LABEL


def test_availability_shape_non_answers_via_missing_time_scope() -> None:
    """A summarize proposal over a real metric with no time scope still rejects.

    The deterministic availability guard is gone; the data-availability question
    shape now reaches the provider, and the surviving time-scope gate (ADR-0011)
    rejects it as MISSING_TIME_SCOPE rather than returning a Success.
    """
    proposal = question_interpreter.ProviderProposal(
        intent="summarize",
        metric="total revenue",
        all_time=False,
        field_operations=(),
    )

    result = question_interpreter.interpret_question(
        question="What months do have revenue data?",
        semantic_layer=_retail_style_semantic_layer(),
        provider=_StaticProvider(proposal),
    )

    assert isinstance(result, contracts.NonAnswer)
    assert result.reason_code == contracts.NonAnswerReasonCode.MISSING_TIME_SCOPE


def test_rank_shape_non_answers_via_unsupported_intent() -> None:
    """A rank proposal still rejects, now through provider-output validation.

    The deterministic rank guard is gone; a non-summarize intent reaches the
    surviving intent gate, which rejects it as UNSUPPORTED_INTENT.
    """
    proposal = question_interpreter.ProviderProposal(
        intent="rank",
        metric="total revenue",
        field_operations=(
            question_interpreter.ProviderFieldOperation(
                operation="range_filter",
                field="order date",
                lower="2026-01-01",
                upper="2026-01-31",
            ),
        ),
    )

    result = question_interpreter.interpret_question(
        question="Which region had the highest total revenue in January 2026?",
        semantic_layer=_retail_style_semantic_layer(),
        provider=_StaticProvider(proposal),
    )

    assert isinstance(result, contracts.NonAnswer)
    assert result.reason_code == contracts.NonAnswerReasonCode.UNSUPPORTED_INTENT


def test_unsupported_data_shape_non_answers_via_unknown_semantic_label() -> None:
    """A summarize proposal over an unknown metric label still rejects.

    The deterministic unsupported-data guard is gone; a label outside the
    Semantic Layer reaches the surviving label gate, which rejects it as
    UNKNOWN_SEMANTIC_LABEL.
    """
    proposal = question_interpreter.ProviderProposal(
        intent="summarize",
        metric="rows in my uploaded csv",
        field_operations=(
            question_interpreter.ProviderFieldOperation(
                operation="range_filter",
                field="order date",
                lower="2026-01-01",
                upper="2026-01-31",
            ),
        ),
    )

    result = question_interpreter.interpret_question(
        question="How many rows are in the CSV I uploaded?",
        semantic_layer=_retail_style_semantic_layer(),
        provider=_StaticProvider(proposal),
    )

    assert isinstance(result, contracts.NonAnswer)
    assert result.reason_code == contracts.NonAnswerReasonCode.UNKNOWN_SEMANTIC_LABEL


def test_group_by_requested_on_non_groupable_field_returns_unsupported_operation() -> (
    None
):
    semantic_layer = semantic_layer_testing.semantic_layer_with_table(
        fields=(
            schema.SemanticField(
                field_id="order_date",
                label="order date",
                source_column="order_date",
                data_type=schema.DataType.DATE,
                operations=(
                    schema.FieldOperation.INCLUDE_FILTER,
                    schema.FieldOperation.EXCLUDE_FILTER,
                    schema.FieldOperation.RANGE_FILTER,
                ),
            ),
        )
    )
    proposal = question_interpreter.ProviderProposal(
        intent="summarize",
        metric="total revenue",
        field_operations=(
            question_interpreter.ProviderFieldOperation(
                operation="group_by",
                field="order date",
            ),
            question_interpreter.ProviderFieldOperation(
                operation="range_filter",
                field="order date",
                lower="2026-01-01",
                upper="2026-01-31",
            ),
        ),
    )

    result = question_interpreter.interpret_question(
        question="What was total revenue by order date in January 2026?",
        semantic_layer=semantic_layer,
        provider=_StaticProvider(proposal),
    )

    assert isinstance(result, contracts.NonAnswer)
    assert (
        result.reason_code == contracts.NonAnswerReasonCode.UNSUPPORTED_FIELD_OPERATION
    )

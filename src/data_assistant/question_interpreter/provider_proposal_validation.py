"""Validate Provider Proposals into trusted Question Frames."""

from __future__ import annotations

import datetime

import data_assistant.non_answer_catalog as non_answer_catalog
import data_assistant.question_interpreter._field_operations as field_operations
import data_assistant.question_interpreter._time_scope as time_scope
import data_assistant.question_interpreter.proposals as proposals
import data_assistant.semantic_layer.catalog as semantic_layer_catalog
import data_assistant.workflow.contracts as contracts
from data_assistant.question_interpreter import semantic_context

_SUPPORTED_PROVIDER_INTENTS = frozenset({"catalog_discovery", "rank", "summarize"})


def interpret_question(
    *,
    question: str,
    semantic_layer: semantic_layer_catalog.SemanticLayerCatalog,
    provider: proposals.QuestionInterpreterProvider,
) -> contracts.StageResult[contracts.QuestionFrame]:
    """Apply Provider Proposal Validation to produce a trusted Question Frame."""
    # No deterministic pre-provider rejects (ADR-0023): support-boundary
    # classification has a single source of truth in provider intent
    # classification plus the surviving time-scope, metric-label, and
    # output-validation gates below.
    # Semantic Layer context is intentionally business-facing: labels and
    # examples, not table names, SQL, column names, or access internals.
    semantic_layer_context = semantic_context.build_semantic_layer_context(
        semantic_layer
    )
    try:
        raw_provider_result = provider.propose_question_frame(
            question=question,
            semantic_layer_context=semantic_layer_context,
        )
    except Exception:
        return non_answer_catalog.non_answer(
            contracts.NonAnswerReasonCode.PROVIDER_FAILURE,
            stage=contracts.NonAnswerStage.QUESTION_INTERPRETER,
        )

    # Provider output stays untrusted until Provider Proposal Validation turns
    # it into the trusted Question Frame contract.
    return _validate_provider_result(raw_provider_result, semantic_layer)


def _validate_provider_result(
    raw_provider_result: object,
    semantic_layer: semantic_layer_catalog.SemanticLayerCatalog,
) -> contracts.StageResult[contracts.QuestionFrame]:
    if isinstance(raw_provider_result, proposals.ProviderFailure):
        return contracts.NonAnswer(
            stage=contracts.NonAnswerStage.QUESTION_INTERPRETER,
            reason_code=contracts.NonAnswerReasonCode.PROVIDER_FAILURE,
            context=_provider_failure_context(raw_provider_result),
        )
    if not isinstance(raw_provider_result, proposals.ProviderProposal):
        return non_answer_catalog.non_answer(
            contracts.NonAnswerReasonCode.INVALID_PROVIDER_OUTPUT,
            stage=contracts.NonAnswerStage.QUESTION_INTERPRETER,
        )

    proposal = raw_provider_result
    intent_value = proposal.intent
    metric_value = proposal.metric

    # Apply current workflow limits before promoting to trusted contract.
    if not intent_value:
        return non_answer_catalog.missing_required_field_non_answer(
            "intent",
            stage=contracts.NonAnswerStage.QUESTION_INTERPRETER,
        )
    if intent_value not in _SUPPORTED_PROVIDER_INTENTS:
        return non_answer_catalog.non_answer(
            contracts.NonAnswerReasonCode.UNSUPPORTED_INTENT,
            stage=contracts.NonAnswerStage.QUESTION_INTERPRETER,
        )
    if intent_value == "catalog_discovery":
        return _validate_catalog_discovery(proposal)
    # The interpreter self-reports metric-qualifier ambiguity (ADR-0017).
    # Provider Proposal Validation is trust boundary that acts on it: a
    # reported ambiguity
    # wins over both missing-metric and label-match so we never silently
    # conflate a dropped qualifier (e.g. "net revenue") with the nearest label.
    if proposal.metric_ambiguity:
        return non_answer_catalog.non_answer(
            contracts.NonAnswerReasonCode.AMBIGUOUS_METRIC,
            stage=contracts.NonAnswerStage.QUESTION_INTERPRETER,
        )
    # The interpreter also self-reports a named-but-unavailable metric (#196):
    # the user clearly named a metric we genuinely do not carry. That is an
    # unsupported-label situation, distinct from the qualifier-ambiguity
    # clarification above, so it routes to UNKNOWN_SEMANTIC_LABEL. Checked after
    # metric_ambiguity and before missing-metric/label-match; the two
    # self-reports are mutually exclusive by prompt rule and this explicit order
    # is a safety net.
    if proposal.unknown_metric:
        return non_answer_catalog.unknown_semantic_label_non_answer(
            "metric",
            stage=contracts.NonAnswerStage.QUESTION_INTERPRETER,
        )
    if not metric_value:
        return non_answer_catalog.missing_required_field_non_answer(
            "metric",
            stage=contracts.NonAnswerStage.QUESTION_INTERPRETER,
        )

    # Finally, prove provider labels are real Semantic Layer labels.
    if metric_value not in semantic_context.metric_labels(semantic_layer):
        return non_answer_catalog.unknown_semantic_label_non_answer(
            "metric",
            stage=contracts.NonAnswerStage.QUESTION_INTERPRETER,
        )
    field_filters_result = field_operations.validate_field_filters(
        proposal.field_operations,
        semantic_layer,
    )
    if isinstance(field_filters_result, contracts.NonAnswer):
        return field_filters_result
    group_by_field, validated_filters = field_filters_result

    relative_filters_result = _resolve_relative_window(
        proposal, validated_filters, semantic_layer
    )
    if isinstance(relative_filters_result, contracts.NonAnswer):
        return relative_filters_result
    if relative_filters_result is not None:
        # The interpreter-computed window joins the validated filters as one more
        # typed date range_filter (ADR-0025); downstream time-scope derivation
        # then sees it as any other date filter.
        validated_filters = validated_filters + (relative_filters_result,)
    validated_time_scope = time_scope.derive_time_scope(
        proposal=proposal,
        field_filters=validated_filters,
        semantic_layer=semantic_layer,
    )
    if isinstance(validated_time_scope, contracts.NonAnswer):
        return validated_time_scope
    rank = _validate_rank(
        proposal=proposal,
        intent_value=intent_value,
        group_by_field=group_by_field,
    )
    if isinstance(rank, contracts.NonAnswer):
        return rank

    return contracts.Success(
        contracts.QuestionFrame(
            intent=intent_value,
            metric=metric_value,
            group_by_field=group_by_field,
            field_filters=validated_filters,
            unresolved_ambiguities=(),
            time_scope=validated_time_scope,
            rank=rank,
        )
    )


def _resolve_relative_window(
    proposal: proposals.ProviderProposal,
    validated_filters: tuple[contracts.FieldFilter[str], ...],
    semantic_layer: semantic_layer_catalog.SemanticLayerCatalog,
) -> contracts.RangeFilter[str] | None | contracts.NonAnswer:
    """Type a relative_window into a date RangeFilter, or reject (ADR-0025).

    relative_window is mutually exclusive with a model-emitted date range_filter:
    a proposal carries one or the other, never both. The model classifies; the
    interpreter computes the window from as_of_date.
    """
    relative_window_proposal = proposal.relative_window
    if relative_window_proposal is None:
        return None
    date_field_labels = field_operations.date_field_labels(semantic_layer)
    has_date_range_filter = any(
        isinstance(field_filter, contracts.RangeFilter)
        and field_filter.field in date_field_labels
        for field_filter in validated_filters
    )
    if has_date_range_filter:
        return non_answer_catalog.non_answer(
            contracts.NonAnswerReasonCode.INVALID_PROVIDER_OUTPUT,
            stage=contracts.NonAnswerStage.QUESTION_INTERPRETER,
        )
    return field_operations.resolve_relative_window(
        relative_window_proposal,
        _as_of_date(semantic_layer),
        semantic_layer,
    )


def _as_of_date(
    semantic_layer: semantic_layer_catalog.SemanticLayerCatalog,
) -> datetime.date | None:
    for dataset in semantic_layer.datasets:
        if dataset.as_of_date is not None:
            return dataset.as_of_date
    return None


def _provider_failure_context(
    provider_failure: proposals.ProviderFailure,
) -> tuple[str, ...]:
    if provider_failure.diagnostic_class is None:
        return ("provider failure",)
    return (provider_failure.diagnostic_class.value,)


def _validate_rank(
    *,
    proposal: proposals.ProviderProposal,
    intent_value: str,
    group_by_field: str | None,
) -> contracts.RankSpec | None | contracts.NonAnswer:
    if intent_value != "rank":
        return None
    if group_by_field is None:
        return non_answer_catalog.non_answer(
            contracts.NonAnswerReasonCode.UNSUPPORTED_SHAPE,
            stage=contracts.NonAnswerStage.QUESTION_INTERPRETER,
        )
    if proposal.limit is not None and proposal.limit <= 0:
        return non_answer_catalog.non_answer(
            contracts.NonAnswerReasonCode.INVALID_PROVIDER_OUTPUT,
            stage=contracts.NonAnswerStage.QUESTION_INTERPRETER,
        )
    if proposal.sort_direction is None:
        return non_answer_catalog.missing_required_field_non_answer(
            "sort_direction",
            stage=contracts.NonAnswerStage.QUESTION_INTERPRETER,
        )
    return contracts.RankSpec(
        result_limit=proposal.limit or contracts.DEFAULT_RESULT_LIMIT,
        sort_direction=contracts.SortDirection(proposal.sort_direction),
    )


def _validate_catalog_discovery(
    proposal: proposals.ProviderProposal,
) -> contracts.StageResult[contracts.QuestionFrame]:
    if (
        proposal.metric is not None
        or proposal.metric_ambiguity is not None
        or proposal.unknown_metric is not None
        or proposal.field_operations
        or proposal.limit is not None
        or proposal.sort_direction is not None
        or proposal.all_time
    ):
        return non_answer_catalog.non_answer(
            contracts.NonAnswerReasonCode.INVALID_PROVIDER_OUTPUT,
            stage=contracts.NonAnswerStage.QUESTION_INTERPRETER,
        )

    return contracts.Success(
        contracts.QuestionFrame(
            intent="catalog_discovery",
            metric=None,
            time_scope=None,
            group_by_field=None,
            field_filters=(),
            unresolved_ambiguities=(),
        )
    )

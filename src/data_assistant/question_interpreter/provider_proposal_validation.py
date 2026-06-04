"""Validate Provider Proposals into trusted Question Frames."""

from __future__ import annotations

import data_assistant.non_answer_catalog as non_answer_catalog
import data_assistant.question_interpreter._field_operations as field_operations
import data_assistant.question_interpreter._time_scope as time_scope
import data_assistant.question_interpreter.proposals as proposals
import data_assistant.semantic_layer.catalog as semantic_layer_catalog
import data_assistant.workflow.contracts as contracts
from data_assistant.question_interpreter import semantic_context

_SUPPORTED_PROVIDER_INTENTS = frozenset({"summarize"})


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
    validated_time_scope = time_scope.derive_time_scope(
        proposal=proposal,
        field_filters=validated_filters,
        semantic_layer=semantic_layer,
    )
    if isinstance(validated_time_scope, contracts.NonAnswer):
        return validated_time_scope

    return contracts.Success(
        contracts.QuestionFrame(
            intent=intent_value,
            metric=metric_value,
            group_by_field=group_by_field,
            field_filters=validated_filters,
            unresolved_ambiguities=(),
            time_scope=validated_time_scope,
        )
    )


def _provider_failure_context(
    provider_failure: proposals.ProviderFailure,
) -> tuple[str, ...]:
    if provider_failure.diagnostic_class is None:
        return ("provider failure",)
    return (provider_failure.diagnostic_class.value,)

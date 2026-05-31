"""Canonical non-answer classification helpers."""

from __future__ import annotations

import dataclasses
import typing

import data_assistant.workflow.contracts as contracts


@dataclasses.dataclass(frozen=True)
class _NonAnswerDefinition:
    response_kind: contracts.ResponseKind
    reason: str
    context: tuple[str, ...]
    next_step: str


_StaticReasonCode: typing.TypeAlias = typing.Literal[
    contracts.NonAnswerReasonCode.AMBIGUOUS_DATASET,
    contracts.NonAnswerReasonCode.AMBIGUOUS_TABLE,
    contracts.NonAnswerReasonCode.INVALID_PROVIDER_OUTPUT,
    contracts.NonAnswerReasonCode.NO_MATCHING_DATASET,
    contracts.NonAnswerReasonCode.NO_MATCHING_TABLE,
    contracts.NonAnswerReasonCode.PROVIDER_FAILURE,
    contracts.NonAnswerReasonCode.UNSUPPORTED_DATA,
    contracts.NonAnswerReasonCode.UNSUPPORTED_FIELD_OPERATION,
    contracts.NonAnswerReasonCode.UNSUPPORTED_FILTER,
    contracts.NonAnswerReasonCode.UNSUPPORTED_INTENT,
    contracts.NonAnswerReasonCode.UNSUPPORTED_SHAPE,
]


_DEFINITIONS: dict[contracts.NonAnswerReasonCode, _NonAnswerDefinition] = {
    contracts.NonAnswerReasonCode.ACCESS_DENIED: _NonAnswerDefinition(
        response_kind=contracts.ResponseKind.ACCESS_DENIAL,
        reason="You do not have access to the {dataset} Curated Dataset.",
        context=(),
        next_step=(
            "Ask a data owner to grant Dataset Access or ask about available data."
        ),
    ),
    contracts.NonAnswerReasonCode.AMBIGUOUS_DATASET: _NonAnswerDefinition(
        response_kind=contracts.ResponseKind.CLARIFICATION_NEEDED,
        reason="Multiple Curated Datasets match the Question Frame.",
        context=("curated dataset",),
        next_step="Ask which Curated Dataset should be used.",
    ),
    contracts.NonAnswerReasonCode.AMBIGUOUS_TABLE: _NonAnswerDefinition(
        response_kind=contracts.ResponseKind.CLARIFICATION_NEEDED,
        reason="Multiple Dataset Tables can satisfy the Question Frame.",
        context=("dataset table",),
        next_step="Ask which Dataset Table should be used.",
    ),
    contracts.NonAnswerReasonCode.INVALID_PROVIDER_OUTPUT: _NonAnswerDefinition(
        response_kind=contracts.ResponseKind.UNSUPPORTED,
        reason="The Question Interpreter provider returned invalid output.",
        context=("provider output",),
        next_step="Fix the provider contract before retrying.",
    ),
    contracts.NonAnswerReasonCode.MISSING_REQUIRED_FIELD: _NonAnswerDefinition(
        response_kind=contracts.ResponseKind.CLARIFICATION_NEEDED,
        reason="The Data Question is missing required interpretation details.",
        context=(),
        next_step="Ask a clarification question before selecting data.",
    ),
    contracts.NonAnswerReasonCode.NO_MATCHING_DATASET: _NonAnswerDefinition(
        response_kind=contracts.ResponseKind.UNSUPPORTED,
        reason="No Curated Dataset safely matches the Question Frame.",
        context=("curated dataset",),
        next_step="Ask which approved business data should be used.",
    ),
    contracts.NonAnswerReasonCode.NO_MATCHING_TABLE: _NonAnswerDefinition(
        response_kind=contracts.ResponseKind.UNSUPPORTED,
        reason="No Dataset Table can satisfy the Question Frame.",
        context=("dataset table",),
        next_step="Ask which table-level metric or dimension should be used.",
    ),
    contracts.NonAnswerReasonCode.PROVIDER_FAILURE: _NonAnswerDefinition(
        response_kind=contracts.ResponseKind.UNSUPPORTED,
        reason="The Question Interpreter provider could not produce a proposal.",
        context=("provider failure",),
        next_step="Retry after the provider is available again.",
    ),
    contracts.NonAnswerReasonCode.UNKNOWN_SEMANTIC_LABEL: _NonAnswerDefinition(
        response_kind=contracts.ResponseKind.UNSUPPORTED,
        reason=(
            "The Data Assistant could not match the requested Semantic Layer "
            "labels."
        ),
        context=(),
        next_step="Use exact Semantic Layer metric and dimension labels.",
    ),
    contracts.NonAnswerReasonCode.UNSUPPORTED_DATA: _NonAnswerDefinition(
        response_kind=contracts.ResponseKind.UNSUPPORTED,
        reason="User-provided CSV files are not supported data sources.",
        context=("unsupported data",),
        next_step=(
            "Ask about an approved Curated Dataset in the Semantic Layer instead."
        ),
    ),
    contracts.NonAnswerReasonCode.UNSUPPORTED_FIELD_OPERATION: _NonAnswerDefinition(
        response_kind=contracts.ResponseKind.UNSUPPORTED,
        reason="The Semantic Layer does not allow that operation for the field.",
        context=("semantic field operation",),
        next_step="Use only operations listed for the Semantic Field.",
    ),
    contracts.NonAnswerReasonCode.UNSUPPORTED_FILTER: _NonAnswerDefinition(
        response_kind=contracts.ResponseKind.UNSUPPORTED,
        reason="The Data Assistant does not support that filter yet.",
        context=("supported filter",),
        next_step="Use only supported filters for approved Semantic Fields.",
    ),
    contracts.NonAnswerReasonCode.UNSUPPORTED_INTENT: _NonAnswerDefinition(
        response_kind=contracts.ResponseKind.UNSUPPORTED,
        reason="The Data Assistant does not support that Data Question intent yet.",
        context=("supported intent",),
        next_step="Ask: What was total revenue by region in January 2026?",
    ),
    contracts.NonAnswerReasonCode.UNSUPPORTED_SHAPE: _NonAnswerDefinition(
        response_kind=contracts.ResponseKind.UNSUPPORTED,
        reason="The Data Assistant cannot handle that Question Frame shape yet.",
        context=("question shape",),
        next_step="Ask for one grouping field or a scalar aggregate.",
    ),
}


@dataclasses.dataclass(frozen=True)
class NonAnswerWording:
    """Rendered team-member-facing copy for a Non-Answer."""

    reason: str
    next_step: str


def response_kind_for(
    reason_code: contracts.NonAnswerReasonCode,
) -> contracts.ResponseKind:
    """Return canonical response kind for a non-answer reason code."""
    return _DEFINITIONS[reason_code].response_kind


def render_wording(non_answer: contracts.NonAnswer) -> NonAnswerWording:
    """Render team-member-facing copy from a structured Non-Answer.

    The catalog owns Non-Answer copy; this is the single place that turns a
    reason code (plus any context such as the denied dataset) into prose.
    """
    definition = _DEFINITIONS[non_answer.reason_code]
    reason = definition.reason
    if non_answer.reason_code == contracts.NonAnswerReasonCode.ACCESS_DENIED:
        reason = reason.format(dataset=non_answer.datasets[0])
    return NonAnswerWording(reason=reason, next_step=definition.next_step)


class StaticCatalogWording:
    """Default Non-Answer wording provider backed by the static catalog."""

    def render_wording(self, non_answer: contracts.NonAnswer) -> NonAnswerWording:
        """Render Non-Answer copy from the static catalog."""
        return render_wording(non_answer)


def non_answer(
    reason_code: _StaticReasonCode,
    *,
    stage: contracts.NonAnswerStage,
) -> contracts.NonAnswer:
    definition = _DEFINITIONS[reason_code]
    return contracts.NonAnswer(
        stage=stage,
        reason_code=reason_code,
        context=definition.context,
    )


def access_denied_non_answer(
    dataset_id: str,
    *,
    stage: contracts.NonAnswerStage,
) -> contracts.NonAnswer:
    return contracts.NonAnswer(
        stage=stage,
        reason_code=contracts.NonAnswerReasonCode.ACCESS_DENIED,
        datasets=(dataset_id,),
    )


def missing_required_field_non_answer(
    field_name: str,
    *,
    stage: contracts.NonAnswerStage,
) -> contracts.NonAnswer:
    return contracts.NonAnswer(
        stage=stage,
        reason_code=contracts.NonAnswerReasonCode.MISSING_REQUIRED_FIELD,
        context=(field_name,),
    )


def unknown_semantic_label_non_answer(
    field_name: str,
    *,
    stage: contracts.NonAnswerStage,
) -> contracts.NonAnswer:
    return contracts.NonAnswer(
        stage=stage,
        reason_code=contracts.NonAnswerReasonCode.UNKNOWN_SEMANTIC_LABEL,
        context=(field_name,),
    )

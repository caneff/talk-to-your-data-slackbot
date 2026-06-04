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
    contracts.NonAnswerReasonCode.AMBIGUOUS_METRIC,
    contracts.NonAnswerReasonCode.AMBIGUOUS_TABLE,
    contracts.NonAnswerReasonCode.INVALID_PROVIDER_OUTPUT,
    contracts.NonAnswerReasonCode.MISSING_TIME_SCOPE,
    contracts.NonAnswerReasonCode.NO_MATCHING_DATASET,
    contracts.NonAnswerReasonCode.NO_MATCHING_TABLE,
    contracts.NonAnswerReasonCode.PROVIDER_FAILURE,
    contracts.NonAnswerReasonCode.UNSUPPORTED_FIELD_OPERATION,
    contracts.NonAnswerReasonCode.UNSUPPORTED_FILTER,
    contracts.NonAnswerReasonCode.UNSUPPORTED_INTENT,
    contracts.NonAnswerReasonCode.UNSUPPORTED_SHAPE,
]


_DEFINITIONS: dict[contracts.NonAnswerReasonCode, _NonAnswerDefinition] = {
    contracts.NonAnswerReasonCode.ACCESS_DENIED: _NonAnswerDefinition(
        response_kind=contracts.ResponseKind.ACCESS_DENIAL,
        reason="You do not have access to {dataset}.",
        context=(),
        next_step="Ask a data owner for access, or ask about data you can use.",
    ),
    contracts.NonAnswerReasonCode.AMBIGUOUS_DATASET: _NonAnswerDefinition(
        response_kind=contracts.ResponseKind.CLARIFICATION_NEEDED,
        reason="More than one approved dataset could answer that.",
        context=("curated dataset",),
        next_step="Tell me which dataset to use.",
    ),
    contracts.NonAnswerReasonCode.AMBIGUOUS_METRIC: _NonAnswerDefinition(
        response_kind=contracts.ResponseKind.CLARIFICATION_NEEDED,
        reason="I couldn't tell which measure you meant.",
        context=("semantic metric",),
        next_step=(
            "Tell me which measure to use, such as total net revenue or total "
            "gross revenue."
        ),
    ),
    contracts.NonAnswerReasonCode.AMBIGUOUS_TABLE: _NonAnswerDefinition(
        response_kind=contracts.ResponseKind.CLARIFICATION_NEEDED,
        reason="More than one table could answer that.",
        context=("dataset table",),
        next_step="Tell me which table to use.",
    ),
    contracts.NonAnswerReasonCode.INVALID_PROVIDER_OUTPUT: _NonAnswerDefinition(
        response_kind=contracts.ResponseKind.UNSUPPORTED,
        reason="Something went wrong reading your question.",
        context=("provider output",),
        next_step="Try rephrasing it, or try again shortly.",
    ),
    contracts.NonAnswerReasonCode.MISSING_REQUIRED_FIELD: _NonAnswerDefinition(
        response_kind=contracts.ResponseKind.CLARIFICATION_NEEDED,
        reason="I need a bit more detail to answer that.",
        context=(),
        next_step="Tell me which measure, grouping, or time period to use.",
    ),
    contracts.NonAnswerReasonCode.MISSING_TIME_SCOPE: _NonAnswerDefinition(
        response_kind=contracts.ResponseKind.CLARIFICATION_NEEDED,
        reason="I need a time period before I can answer that.",
        context=("time scope",),
        next_step="Tell me the time period to use, or say that you want all time.",
    ),
    contracts.NonAnswerReasonCode.NO_MATCHING_DATASET: _NonAnswerDefinition(
        response_kind=contracts.ResponseKind.UNSUPPORTED,
        reason="I couldn't find an approved dataset that matches that request.",
        context=("curated dataset",),
        next_step="Try asking about a different approved business dataset.",
    ),
    contracts.NonAnswerReasonCode.NO_MATCHING_TABLE: _NonAnswerDefinition(
        response_kind=contracts.ResponseKind.UNSUPPORTED,
        reason="I couldn't find a table that matches that request.",
        context=("dataset table",),
        next_step="Try naming a different measure or grouping.",
    ),
    contracts.NonAnswerReasonCode.PROVIDER_FAILURE: _NonAnswerDefinition(
        response_kind=contracts.ResponseKind.UNSUPPORTED,
        reason="Something went wrong while reading your question.",
        context=("provider failure",),
        next_step="Try again shortly.",
    ),
    contracts.NonAnswerReasonCode.UNKNOWN_SEMANTIC_LABEL: _NonAnswerDefinition(
        response_kind=contracts.ResponseKind.UNSUPPORTED,
        reason="I couldn't match part of your request to the available data.",
        context=(),
        next_step=(
            "Try naming the measure or grouping more plainly, such as total "
            "revenue by region."
        ),
    ),
    contracts.NonAnswerReasonCode.UNSUPPORTED_FIELD_OPERATION: _NonAnswerDefinition(
        response_kind=contracts.ResponseKind.UNSUPPORTED,
        reason="That breakdown or filter isn't available for that field.",
        context=("semantic field operation",),
        next_step="Try a different grouping.",
    ),
    contracts.NonAnswerReasonCode.UNSUPPORTED_FILTER: _NonAnswerDefinition(
        response_kind=contracts.ResponseKind.UNSUPPORTED,
        reason="The Data Assistant does not support that filter yet.",
        context=("supported filter",),
        next_step="Try a different filter.",
    ),
    contracts.NonAnswerReasonCode.UNSUPPORTED_INTENT: _NonAnswerDefinition(
        response_kind=contracts.ResponseKind.UNSUPPORTED,
        reason="I can't answer that kind of question yet.",
        context=("supported intent",),
        next_step=(
            "Try asking for a measure by a grouping and time period, such as "
            "total revenue by region in January 2026."
        ),
    ),
    contracts.NonAnswerReasonCode.UNSUPPORTED_SHAPE: _NonAnswerDefinition(
        response_kind=contracts.ResponseKind.UNSUPPORTED,
        reason="I can't answer that question shape yet.",
        context=("question shape",),
        next_step="Try asking for one grouping or a single total.",
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

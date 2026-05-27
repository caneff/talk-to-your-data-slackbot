"""Response Composer for Data Assistant Answer Drafts."""

from __future__ import annotations

import data_assistant.workflow.contracts as contracts


def compose_final_response(
    answer_draft: contracts.AnswerDraft,
) -> contracts.FinalResponse:
    """Compose a concise plain-text Final Response with a Trust Summary."""
    formatted_metric_values = answer_draft.key_data["metric_value"].astype(float).map(
        _format_money,
    )
    revenue_lines = "\n".join(
        "- "
        + answer_draft.key_data["dimension_value"].astype(str)
        + ": "
        + formatted_metric_values,
    )
    trust_summary = contracts.TrustSummary(
        datasets=answer_draft.datasets_used,
        dataset_tables=answer_draft.dataset_tables_used,
        time_range=answer_draft.time_range,
        filters=answer_draft.filters,
        freshness=answer_draft.freshness,
        caveats=answer_draft.caveats,
        limitations=answer_draft.limitations,
    )
    text = (
        f"{answer_draft.summary}\n\n{revenue_lines}\n\n"
        f"{render_trust_summary(trust_summary)}"
    )

    return contracts.FinalResponse(
        text=text,
        trust_summary=trust_summary,
        response_kind="answer",
    )


def compose_non_answer_response(
    non_answer: contracts.NonAnswer,
) -> contracts.FinalResponse:
    """Compose a plain-text Final Response for a workflow Non-Answer."""
    adverb = (
        " yet"
        if non_answer.reason
        == "The Data Question is missing required interpretation details."
        else ""
    )
    reason = non_answer.reason[0].lower() + non_answer.reason[1:]
    response_kind = _response_kind_for_non_answer(non_answer)
    trust_summary = contracts.TrustSummary(
        datasets=non_answer.datasets,
        limitations=(non_answer.reason,),
    )
    text = (
        f"I cannot answer safely{adverb} because {reason}\n\n"
        f"Next step: {non_answer.next_step}\n\n"
        f"{render_trust_summary(trust_summary)}"
    )
    return contracts.FinalResponse(
        text=text,
        trust_summary=trust_summary,
        response_kind=response_kind,
    )


def render_trust_summary(trust_summary: contracts.TrustSummary) -> str:
    """Render structured trust summary data for Slack-facing plain text."""
    segments: list[str] = []
    if trust_summary.datasets:
        segments.append(f"Curated Dataset: {', '.join(trust_summary.datasets)}.")
    if trust_summary.dataset_tables:
        segments.append(f"Dataset Table: {', '.join(trust_summary.dataset_tables)}.")
    if trust_summary.time_range is not None:
        segments.append(f"Time range: {trust_summary.time_range}.")
    if trust_summary.filters:
        segments.append(f"Filters: {', '.join(trust_summary.filters)}.")
    if trust_summary.freshness is not None:
        segments.append(f"Freshness: {trust_summary.freshness}")
    if trust_summary.caveats:
        segments.append(f"Caveats: {' '.join(trust_summary.caveats)}")
    if trust_summary.limitations:
        segments.append(f"Limitations: {' '.join(trust_summary.limitations)}")
    return "Trust Summary: " + " ".join(segments)


def _response_kind_for_non_answer(non_answer: contracts.NonAnswer) -> str:
    if non_answer.stage == contracts.NonAnswerStage.ACCESS_CONTROLLER:
        return "access_denial"
    if non_answer.unresolved_ambiguities == ("time range",):
        return "clarification_needed"
    return "unsupported"


def _format_money(value: float) -> str:
    return f"${value:,.2f}"

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
    filters = ", ".join(answer_draft.filters) if answer_draft.filters else "none"
    caveats = " ".join(answer_draft.caveats)
    datasets = ", ".join(answer_draft.datasets_used)
    dataset_tables = ", ".join(answer_draft.dataset_tables_used)
    trust_summary = (
        "Trust Summary: "
        f"Curated Dataset: {datasets}. "
        f"Dataset Table: {dataset_tables}. "
        f"Time range: {answer_draft.time_range}. "
        f"Filters: {filters}. "
        f"Caveats: {caveats}"
    )
    text = f"{answer_draft.summary}\n\n{revenue_lines}\n\n{trust_summary}"

    return contracts.FinalResponse(text=text, trust_summary=trust_summary)


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
    text = (
        f"I cannot answer safely{adverb} because {reason}\n\n"
        f"Next step: {non_answer.next_step}"
    )
    trust_summary = (
        "Trust Summary: Returned a Non-Answer Response from "
        f"{non_answer.stage}."
    )
    return contracts.FinalResponse(text=text, trust_summary=trust_summary)


def _format_money(value: float) -> str:
    return f"${value:,.2f}"

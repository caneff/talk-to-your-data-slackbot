"""Response Composer for clean commerce Answer Drafts."""

from __future__ import annotations

import decimal

from talk_to_your_data_slackbot.clean_commerce_spine import contracts


def compose_final_response(
    answer_draft: contracts.AnswerDraft,
) -> contracts.FinalResponse:
    """Compose a concise plain-text Final Response with a Trust Summary."""
    revenue_lines = "\n".join(
        f"- {row.region}: {_format_money(row.total_revenue)}"
        for row in answer_draft.key_numbers
    )
    filters = ", ".join(answer_draft.filters) if answer_draft.filters else "none"
    caveats = " ".join(answer_draft.caveats)
    datasets = ", ".join(answer_draft.datasets_used)
    trust_summary = (
        "Trust Summary: "
        f"Curated Dataset: {datasets}. "
        f"Time range: {answer_draft.time_range}. "
        f"Filters: {filters}. "
        f"Caveats: {caveats}"
    )
    text = f"{answer_draft.summary}\n\n{revenue_lines}\n\n{trust_summary}"

    return contracts.FinalResponse(text=text, trust_summary=trust_summary)


def _format_money(value: decimal.Decimal) -> str:
    return f"${value:,.2f}"

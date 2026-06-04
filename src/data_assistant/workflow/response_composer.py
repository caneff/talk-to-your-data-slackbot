"""Response Composer for Data Assistant Answer Drafts."""

from __future__ import annotations

import typing

import pandas as pd

import data_assistant.metric_formatter as metric_formatter
import data_assistant.non_answer_catalog as non_answer_catalog
import data_assistant.workflow.contracts as contracts


class NonAnswerWordingProvider(typing.Protocol):
    """Provider boundary for Non-Answer team-member-facing copy."""

    def render_wording(
        self,
        non_answer: contracts.NonAnswer,
    ) -> non_answer_catalog.NonAnswerWording:
        """Return rendered copy for a structured Non-Answer."""
        ...


def compose_final_response(
    answer_draft: contracts.AnswerDraft,
) -> contracts.FinalResponse:
    """Compose a Slack-ready Final Response with a Trust Summary fallback."""
    formatted_metric_values = (
        answer_draft.key_data["metric_value"]
        .astype(float)
        .map(
            lambda value: metric_formatter.format_metric_value(
                value,
                answer_draft.metric_kind,
            ),
        )
    )
    metric_lines = "\n".join(
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
        caveats=answer_draft.caveats,
        limitations=answer_draft.limitations,
    )
    rendered_trust_summary = render_trust_summary(trust_summary)
    if metric_lines:
        text = f"{answer_draft.summary}\n\n{metric_lines}\n\n{rendered_trust_summary}"
    else:
        text = f"{answer_draft.summary}\n\n{rendered_trust_summary}"

    return contracts.FinalResponse(
        text=text,
        trust_summary=trust_summary,
        response_kind=contracts.ResponseKind.ANSWER,
        blocks=_render_answer_blocks(
            summary=answer_draft.summary,
            trust_summary=rendered_trust_summary,
            table_blocks=_render_key_data_table_block(
                answer_draft.key_data,
                formatted_metric_values,
                dimension_header=answer_draft.group_by_label or "Group",
                metric_header=answer_draft.metric_label,
            ),
        ),
    )


def compose_non_answer_response(
    non_answer: contracts.NonAnswer,
    *,
    wording_provider: NonAnswerWordingProvider,
) -> contracts.FinalResponse:
    """Compose a plain-text Final Response for a workflow Non-Answer."""
    response_kind = non_answer_catalog.response_kind_for(non_answer.reason_code)
    wording = wording_provider.render_wording(non_answer)
    adverb = (
        " yet" if response_kind == contracts.ResponseKind.CLARIFICATION_NEEDED else ""
    )
    reason = wording.reason[0].lower() + wording.reason[1:]
    trust_summary = contracts.TrustSummary(
        datasets=non_answer.datasets,
        limitations=(wording.reason,),
    )
    text = (
        f"I cannot answer safely{adverb} because {reason}\n\n"
        f"Next step: {wording.next_step}\n\n"
        f"{render_trust_summary(trust_summary)}"
    )
    return contracts.FinalResponse(
        text=text,
        trust_summary=trust_summary,
        response_kind=response_kind,
        non_answer=non_answer,
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
    if trust_summary.caveats:
        segments.append(f"Caveats: {' '.join(trust_summary.caveats)}")
    if trust_summary.limitations:
        segments.append(f"Limitations: {' '.join(trust_summary.limitations)}")
    return "Trust Summary: " + " ".join(segments)


def _render_answer_blocks(
    *,
    summary: str,
    trust_summary: str,
    table_blocks: tuple[contracts.SlackBlock, ...],
) -> tuple[contracts.SlackBlock, ...]:
    return (
        {
            "type": "section",
            "text": {
                "type": "plain_text",
                "text": summary,
            },
        },
        {
            "type": "context",
            "elements": [
                {
                    "type": "plain_text",
                    "text": trust_summary,
                },
            ],
        },
        *table_blocks,
    )


def _render_key_data_table_block(
    key_data: pd.DataFrame,
    formatted_metric_values: pd.Series,
    *,
    dimension_header: str,
    metric_header: str,
) -> tuple[contracts.SlackBlock, ...]:
    rows = [
        [
            {"type": "raw_text", "text": _title_case_label(dimension_header)},
            {"type": "raw_text", "text": _title_case_label(metric_header)},
        ],
    ]
    rows.extend(
        [
            {"type": "raw_text", "text": str(dimension_value)},
            {"type": "raw_text", "text": str(metric_value)},
        ]
        for dimension_value, metric_value in zip(
            key_data["dimension_value"],
            formatted_metric_values,
            strict=True,
        )
    )
    if len(rows) == 1 or len(rows) > 100:
        return ()
    return (
        {
            "type": "table",
            "column_settings": [
                {"is_wrapped": True},
                {"align": "right"},
            ],
            "rows": rows,
        },
    )


def _title_case_label(label: str) -> str:
    return " ".join(word[:1].upper() + word[1:] for word in label.split(" "))

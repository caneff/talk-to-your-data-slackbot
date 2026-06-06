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
    # Ungrouped single-total answers carry one "All" row whose metric just
    # repeats the headline number the summary already states. Suppress the
    # redundant bullet and key-data table for that case (issue #275).
    is_ungrouped = answer_draft.group_by_label is None
    metric_lines = (
        ""
        if is_ungrouped
        else "\n".join(
            _metric_line(
                index=index,
                dimension_value=dimension_value,
                metric_value=metric_value,
                rank=answer_draft.rank,
            )
            for index, (dimension_value, metric_value) in enumerate(
                zip(
                    answer_draft.key_data["dimension_value"].astype(str),
                    formatted_metric_values,
                    strict=True,
                ),
                start=1,
            )
        )
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
            table_blocks=(
                ()
                if is_ungrouped
                else _render_key_data_table_block(
                    answer_draft.key_data,
                    formatted_metric_values,
                    dimension_header=answer_draft.group_by_label or "Group",
                    metric_header=answer_draft.metric_label,
                    rank=answer_draft.rank,
                )
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
    reason = _lowercase_leading_word(wording.reason)
    trust_summary = contracts.TrustSummary(
        datasets=non_answer.datasets,
        limitations=(wording.reason,),
    )
    rendered_trust_summary = render_trust_summary(trust_summary)
    body = (
        f"I cannot answer safely{adverb} because {reason}\n\n"
        f"Next step: {wording.next_step}"
    )
    text = f"{body}\n\n{rendered_trust_summary}"
    return contracts.FinalResponse(
        text=text,
        trust_summary=trust_summary,
        response_kind=response_kind,
        non_answer=non_answer,
        blocks=_render_body_with_trust_blocks(
            body=body,
            trust_summary=rendered_trust_summary,
        ),
    )


def compose_catalog_discovery_response(
    *,
    datasets: tuple[contracts.CatalogDatasetSummary, ...],
) -> contracts.FinalResponse:
    """Compose metadata-only catalog discovery response with compact blocks."""
    if not datasets:
        trust_summary = contracts.TrustSummary(
            limitations=(
                "Semantic Layer metadata used.",
                "Curated Dataset names shown: none.",
                "Prepared Data was not read.",
            ),
        )
        trust_text = (
            "Trust Summary: Semantic Layer metadata used. Curated Dataset names "
            "shown: none. Prepared Data was not read."
        )
        return contracts.FinalResponse(
            text=(
                "No approved datasets are currently available for you to query."
                "\n\n"
                f"{trust_text}"
            ),
            trust_summary=trust_summary,
            response_kind=contracts.ResponseKind.ANSWER,
            blocks=(
                {
                    "type": "section",
                    "text": {
                        "type": "plain_text",
                        "text": (
                            "No approved datasets are currently available for "
                            "you to query."
                        ),
                    },
                },
                {
                    "type": "context",
                    "elements": [
                        {
                            "type": "plain_text",
                            "text": trust_text,
                        },
                    ],
                },
            ),
        )

    dataset_names = tuple(dataset.dataset_name for dataset in datasets)
    trust_text = (
        "Trust Summary: Semantic Layer metadata used. Curated Dataset names "
        f"shown: {', '.join(dataset_names)}. Prepared Data was not read. "
        "Examples were curated or generated from approved Semantic Layer labels."
    )
    trust_summary = contracts.TrustSummary(
        datasets=dataset_names,
        limitations=(
            "Semantic Layer metadata used.",
            "Prepared Data was not read.",
            "Examples were curated or generated from approved Semantic Layer labels.",
        ),
    )
    sections = tuple(_render_catalog_dataset_block(dataset) for dataset in datasets)
    text = "\n\n".join(
        (
            "You can query these approved datasets:",
            *(_render_catalog_dataset_text(dataset) for dataset in datasets),
            trust_text,
        )
    )
    return contracts.FinalResponse(
        text=text,
        trust_summary=trust_summary,
        response_kind=contracts.ResponseKind.ANSWER,
        blocks=(
            *sections,
            {
                "type": "context",
                "elements": [
                    {
                        "type": "plain_text",
                        "text": trust_text,
                    },
                ],
            },
        ),
    )


def _lowercase_leading_word(reason: str) -> str:
    """Lowercase the reason's first char for inline use after ``because``.

    Skips the lowercasing when the first word is the standalone pronoun ``I``
    so the body reads ``because I need …`` (not ``because i need …``). The
    carve-out applies only to the bare pronoun (``I``, ``I'd``, ``I'm``), not
    real leading words like ``Inventory`` (issue #276).
    """
    if reason[:1] == "I" and (len(reason) == 1 or reason[1] in (" ", "'")):
        return reason
    return reason[:1].lower() + reason[1:]


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
        *_render_body_with_trust_blocks(body=summary, trust_summary=trust_summary),
        *table_blocks,
    )


def _render_body_with_trust_blocks(
    *,
    body: str,
    trust_summary: str,
) -> tuple[contracts.SlackBlock, ...]:
    """Render a body ``section`` plus the Trust Summary ``context`` footer.

    Shared by the answer and Non-Answer paths so both present the Trust Summary
    in the same small grey ``context`` block (issue #276).
    """
    return (
        {
            "type": "section",
            "text": {
                "type": "plain_text",
                "text": body,
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
    )


def _render_key_data_table_block(
    key_data: pd.DataFrame,
    formatted_metric_values: pd.Series,
    *,
    dimension_header: str,
    metric_header: str,
    rank: contracts.RankSpec | None,
) -> tuple[contracts.SlackBlock, ...]:
    header_row: list[dict[str, str]] = []
    column_settings: list[dict[str, object]] = []
    if rank is not None:
        header_row.append({"type": "raw_text", "text": "#"})
        column_settings.append({"align": "right"})
    header_row.extend(
        (
            {"type": "raw_text", "text": _title_case_label(dimension_header)},
            {"type": "raw_text", "text": _title_case_label(metric_header)},
        )
    )
    column_settings.extend(
        (
            {"is_wrapped": True},
            {"align": "right"},
        )
    )
    rows = [header_row]
    for index, (dimension_value, metric_value) in enumerate(
        zip(
            key_data["dimension_value"],
            formatted_metric_values,
            strict=True,
        ),
        start=1,
    ):
        row: list[dict[str, str]] = []
        if rank is not None:
            row.append({"type": "raw_text", "text": str(index)})
        row.extend(
            (
                {"type": "raw_text", "text": str(dimension_value)},
                {"type": "raw_text", "text": str(metric_value)},
            )
        )
        rows.append(row)
    if len(rows) == 1 or len(rows) > 100:
        return ()
    return (
        {
            "type": "table",
            "column_settings": column_settings,
            "rows": rows,
        },
    )


def _metric_line(
    *,
    index: int,
    dimension_value: str,
    metric_value: str,
    rank: contracts.RankSpec | None,
) -> str:
    prefix = "- " if rank is None else f"{index}. "
    return f"{prefix}{dimension_value}: {metric_value}"


def _title_case_label(label: str) -> str:
    return " ".join(word[:1].upper() + word[1:] for word in label.split(" "))


def _render_catalog_dataset_block(
    dataset: contracts.CatalogDatasetSummary,
) -> contracts.SlackBlock:
    return {
        "type": "section",
        "text": {
            "type": "mrkdwn",
            "text": _render_catalog_dataset_text(dataset),
        },
    }


def _render_catalog_dataset_text(
    dataset: contracts.CatalogDatasetSummary,
) -> str:
    example_lines = "\n".join(f"- {question}" for question in dataset.example_questions)
    return (
        f"*{dataset.dataset_name}*\n"
        f"Information types: {', '.join(dataset.information_types)}\n"
        f"Metrics: {', '.join(dataset.metric_labels)}\n"
        f"Fields: {', '.join(dataset.field_labels)}\n"
        f"Example questions:\n{example_lines}"
    )

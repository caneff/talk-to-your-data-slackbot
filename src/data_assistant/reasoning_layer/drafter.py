"""Reasoning Layer drafting: deterministic floor and grounded narration."""

from __future__ import annotations

import dataclasses

import data_assistant.reasoning_layer.proposals as proposals
import data_assistant.workflow.contracts as contracts

# Caveat appended when a generated narrative is withheld and the answer
# degrades visibly to the deterministic template (see ADR-0012).
WITHHELD_WORDING_CAVEAT = (
    "Phrased from a standard template; generated wording was withheld."
)


def draft_answer(
    prepared_data: contracts.PreparedData,
) -> contracts.AnswerDraft:
    """Produce a deterministic Answer Draft from Prepared Data."""
    slot_values = proposals.compute_slot_values(prepared_data)
    summary = _template_summary(prepared_data, slot_values)
    return _answer_draft(prepared_data, summary, slot_values)


def draft_narrative(
    prepared_data: contracts.PreparedData,
    *,
    provider: proposals.ReasoningProvider,
) -> contracts.AnswerDraft:
    """Narrate Prepared Data via the provider, grounded against the floor.

    Propose prose around the Narrative Slots, ground it (any digit fails),
    fill the slots deterministically, and degrade visibly to the template
    answer on provider failure, grounding violation, or an unfillable
    proposal (an unknown slot or a malformed brace).
    """
    slot_values = proposals.compute_slot_values(prepared_data)
    template_summary = _template_summary(prepared_data, slot_values)
    deterministic_draft = _answer_draft(prepared_data, template_summary, slot_values)

    result_shape = proposals.figure_free_result_shape(slot_values)
    proposal = provider.propose_narrative(result_shape=result_shape)

    if isinstance(proposal, proposals.ProviderFailure):
        return _with_withheld_caveat(deterministic_draft)
    if not proposals.proposal_is_grounded(proposal):
        return _with_withheld_caveat(deterministic_draft)

    filled = proposals.fill_narrative(proposal, slot_values)
    if filled is None:
        return _with_withheld_caveat(deterministic_draft)
    return dataclasses.replace(deterministic_draft, summary=filled)


def _template_summary(
    prepared_data: contracts.PreparedData,
    slot_values: dict[str, object],
) -> str:
    if prepared_data.request.group_by_fields:
        template = (
            "{metric} in {time_range} was {metric_total}, grouped across "
            "{dimension_count} {dimension}."
        )
    else:
        template = "{metric} in {time_range} was {metric_total}."
    return template.format_map(slot_values)


def _answer_draft(
    prepared_data: contracts.PreparedData,
    summary: str,
    slot_values: dict[str, object],
) -> contracts.AnswerDraft:
    request = prepared_data.request
    time_range = str(slot_values["time_range"])
    return contracts.AnswerDraft(
        summary=summary,
        key_data=prepared_data.data,
        datasets_used=(request.dataset.name,),
        dataset_tables_used=(request.table.table_id,),
        metric_kind=request.metric.kind,
        time_range=time_range,
        filters=request.filter_labels,
        freshness=request.dataset.freshness.description,
        caveats=prepared_data.quality_notes,
    )


def _with_withheld_caveat(
    answer_draft: contracts.AnswerDraft,
) -> contracts.AnswerDraft:
    return dataclasses.replace(
        answer_draft,
        caveats=(*answer_draft.caveats, WITHHELD_WORDING_CAVEAT),
    )

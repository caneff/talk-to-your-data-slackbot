"""Internal Provider Proposal time-scope validation helpers."""

from __future__ import annotations

import data_assistant.non_answer_catalog as non_answer_catalog
import data_assistant.question_interpreter.proposals as proposals
import data_assistant.semantic_layer.catalog as semantic_layer_catalog
import data_assistant.semantic_layer.schema as schema
import data_assistant.workflow.contracts as contracts


def derive_time_scope(
    *,
    proposal: proposals.ProviderProposal,
    field_filters: tuple[contracts.FieldFilter[str], ...],
    semantic_layer: semantic_layer_catalog.SemanticLayerCatalog,
) -> contracts.TimeScope | contracts.NonAnswer:
    date_field_labels = {
        field.label
        for table in semantic_layer.tables
        for field in table.fields
        if field.data_type == schema.DataType.DATE
    }
    has_date_filter = any(
        field_filter.field in date_field_labels for field_filter in field_filters
    )
    if has_date_filter and proposal.all_time:
        return non_answer_catalog.non_answer(
            contracts.NonAnswerReasonCode.INVALID_PROVIDER_OUTPUT,
            stage=contracts.NonAnswerStage.QUESTION_INTERPRETER,
        )
    if has_date_filter:
        return contracts.TimeScope.BOUNDED
    if proposal.all_time:
        return contracts.TimeScope.ALL_TIME
    return non_answer_catalog.non_answer(
        contracts.NonAnswerReasonCode.MISSING_TIME_SCOPE,
        stage=contracts.NonAnswerStage.QUESTION_INTERPRETER,
    )

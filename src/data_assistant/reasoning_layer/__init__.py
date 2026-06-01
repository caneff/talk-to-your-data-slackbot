"""Reasoning Layer package facade."""

from data_assistant.reasoning_layer.drafter import (
    WITHHELD_WORDING_CAVEAT,
    draft_answer,
    draft_narrative,
)
from data_assistant.reasoning_layer.proposals import (
    NarrativeProposal,
    ProviderFailure,
    ReasoningProvider,
    compute_slot_values,
    figure_free_result_shape,
    proposal_is_grounded,
)

__all__ = [
    "WITHHELD_WORDING_CAVEAT",
    "NarrativeProposal",
    "ProviderFailure",
    "ReasoningProvider",
    "compute_slot_values",
    "draft_answer",
    "draft_narrative",
    "figure_free_result_shape",
    "proposal_is_grounded",
]

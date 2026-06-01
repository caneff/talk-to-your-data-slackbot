"""Reasoning Layer package facade."""

from data_assistant.reasoning_layer.drafter import (
    WITHHELD_WORDING_CAVEAT,
    draft_answer,
    draft_narrative,
)
from data_assistant.reasoning_layer.openai_provider import (
    OpenAIReasoningConfig,
    OpenAIReasoningConfigError,
    OpenAIReasoningProvider,
    build_openai_reasoning_provider,
    load_openai_reasoning_config,
)
from data_assistant.reasoning_layer.proposals import (
    NarrativeProposal,
    ProviderFailure,
    ReasoningProvider,
    compute_slot_values,
    figure_free_result_shape,
    fill_narrative,
    proposal_is_grounded,
)

__all__ = [
    "WITHHELD_WORDING_CAVEAT",
    "NarrativeProposal",
    "OpenAIReasoningConfig",
    "OpenAIReasoningConfigError",
    "OpenAIReasoningProvider",
    "ProviderFailure",
    "ReasoningProvider",
    "build_openai_reasoning_provider",
    "compute_slot_values",
    "draft_answer",
    "draft_narrative",
    "figure_free_result_shape",
    "fill_narrative",
    "load_openai_reasoning_config",
    "proposal_is_grounded",
]

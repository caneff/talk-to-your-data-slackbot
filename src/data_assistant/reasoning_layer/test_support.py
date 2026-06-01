"""Shared fixtures and builders for Reasoning Layer tests.

These helpers keep behavior-focused test files from repeating fake provider
stubs and default proposal construction, mirroring the Question Interpreter
test support.
"""

import data_assistant.reasoning_layer as reasoning_layer


def fixed_narrative_provider(
    provider_proposal: reasoning_layer.NarrativeProposal,
) -> reasoning_layer.ReasoningProvider:
    """Build a fake provider that always returns one fixed proposal."""

    class FixedNarrativeProvider:
        def propose_narrative(
            self,
            *,
            result_shape: dict[str, object],
        ) -> reasoning_layer.NarrativeProposal:
            del result_shape
            return provider_proposal

    return FixedNarrativeProvider()


def provider_failure_provider(
    reason: str = "provider unavailable",
) -> reasoning_layer.ReasoningProvider:
    """Build a fake provider that returns a ProviderFailure."""

    class ProviderFailureProvider:
        def propose_narrative(
            self,
            *,
            result_shape: dict[str, object],
        ) -> reasoning_layer.ProviderFailure:
            del result_shape
            return reasoning_layer.ProviderFailure(reason=reason)

    return ProviderFailureProvider()


def narrative_proposal(
    *,
    summary: str = (
        "{metric} in {time_range} spanned {dimension_count} {dimension}, "
        "led by {top_dimension}."
    ),
) -> reasoning_layer.NarrativeProposal:
    """Build a valid, grounded, slot-only proposal for tests."""
    return reasoning_layer.NarrativeProposal(summary=summary)

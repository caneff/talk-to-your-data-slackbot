"""OpenAI-backed Reasoning Layer narrative provider."""

from __future__ import annotations

import collections.abc
import dataclasses
import json

import data_assistant.openai_support as openai_support
from data_assistant.openai_support import OpenAIInputMessage
from data_assistant.reasoning_layer.proposals import (
    NarrativeProposal,
    ProviderFailure,
)

# Module-local private alias for the shared client protocol; the deterministic
# provider tests cast injected fakes to this same-module name.
_OpenAIClient = openai_support.OpenAIClient

_REASONING_LAYER_DEVELOPER_PROMPT = "reasoning_layer_developer.md"


@dataclasses.dataclass(frozen=True)
class OpenAIReasoningConfig:
    """Environment-backed config for the OpenAI Reasoning Layer provider."""

    api_key: str
    model: str
    timeout_seconds: float = 15.0
    max_retries: int = 1


class OpenAIReasoningConfigError(ValueError):
    """Raised when required OpenAI provider config is missing."""


def load_openai_reasoning_config(
    environ: collections.abc.Mapping[str, str],
) -> OpenAIReasoningConfig:
    """Load required OpenAI provider config from environment variables."""
    api_key = openai_support.require_api_key(environ, OpenAIReasoningConfigError)
    return OpenAIReasoningConfig(
        api_key=api_key,
        model=environ.get("OPENAI_MODEL", openai_support.DEFAULT_OPENAI_MODEL),
        timeout_seconds=openai_support.parse_timeout_seconds(
            environ, OpenAIReasoningConfigError
        ),
        max_retries=openai_support.parse_max_retries(
            environ, OpenAIReasoningConfigError
        ),
    )


class OpenAIReasoningProvider:
    """OpenAI-backed Reasoning Layer narrative provider."""

    def __init__(
        self,
        *,
        config: OpenAIReasoningConfig,
        client: _OpenAIClient,
    ) -> None:
        self._config = config
        self._client = client

    def propose_narrative(
        self,
        *,
        result_shape: dict[str, object],
    ) -> NarrativeProposal | ProviderFailure:
        return openai_support.run_parse(
            client=self._client,
            model=self._config.model,
            input_messages=_build_openai_input(result_shape=result_shape),
            text_format=NarrativeProposal,
            failure_factory=lambda reason: ProviderFailure(reason=reason),
        )


def _build_openai_input(
    *,
    result_shape: dict[str, object],
) -> list[OpenAIInputMessage]:
    return [
        openai_support.developer_message(_REASONING_LAYER_DEVELOPER_PROMPT),
        _user_message(result_shape=result_shape),
    ]


def _user_message(
    *,
    result_shape: dict[str, object],
) -> OpenAIInputMessage:
    return {
        "role": "user",
        "content": json.dumps({"result_shape": result_shape}, sort_keys=True),
    }


def build_openai_reasoning_provider(
    environ: collections.abc.Mapping[str, str],
    *,
    client: _OpenAIClient | None = None,
) -> OpenAIReasoningProvider:
    """Build the OpenAI provider with env-backed config and SDK client."""
    config = load_openai_reasoning_config(environ)
    return OpenAIReasoningProvider(
        config=config,
        client=client or openai_support.build_openai_client(config),
    )

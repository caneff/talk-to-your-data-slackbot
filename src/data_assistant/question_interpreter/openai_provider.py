"""OpenAI-backed Question Interpreter provider."""

from __future__ import annotations

import collections.abc
import dataclasses
import json

import data_assistant.openai_support as openai_support
from data_assistant.openai_support import OpenAIInputMessage
from data_assistant.question_interpreter.proposals import (
    ProviderFailure,
    ProviderFailureDiagnosticClass,
    ProviderProposal,
)

# Module-local private alias for the shared client protocol; the deterministic
# provider tests cast injected fakes to this same-module name.
_OpenAIClient = openai_support.OpenAIClient

_STRUCTURED_OUTPUT_ATTEMPTS = 2
_QUESTION_INTERPRETER_DEVELOPER_PROMPT = "question_interpreter_developer.md"


@dataclasses.dataclass(frozen=True)
class OpenAIQuestionInterpreterConfig:
    """Environment-backed config for the OpenAI Question Interpreter provider."""

    api_key: str
    model: str
    timeout_seconds: float = 15.0
    max_retries: int = 1


class OpenAIQuestionInterpreterConfigError(ValueError):
    """Raised when required OpenAI provider config is missing."""


def load_openai_question_interpreter_config(
    environ: collections.abc.Mapping[str, str],
) -> OpenAIQuestionInterpreterConfig:
    """Load required OpenAI provider config from environment variables."""
    api_key = openai_support.require_api_key(
        environ, OpenAIQuestionInterpreterConfigError
    )
    return OpenAIQuestionInterpreterConfig(
        api_key=api_key,
        model=environ.get("OPENAI_MODEL", openai_support.DEFAULT_OPENAI_MODEL),
        timeout_seconds=openai_support.parse_timeout_seconds(
            environ, OpenAIQuestionInterpreterConfigError
        ),
        max_retries=openai_support.parse_max_retries(
            environ, OpenAIQuestionInterpreterConfigError
        ),
    )


class OpenAIQuestionInterpreterProvider:
    """OpenAI-backed Question Interpreter provider."""

    def __init__(
        self,
        *,
        config: OpenAIQuestionInterpreterConfig,
        client: _OpenAIClient,
    ) -> None:
        self._config = config
        self._client = client

    def propose_question_frame(
        self,
        *,
        question: str,
        semantic_layer_context: dict[str, object],
    ) -> ProviderProposal | ProviderFailure:
        return openai_support.run_parse(
            client=self._client,
            model=self._config.model,
            input_messages=_build_openai_input(
                question=question,
                semantic_layer_context=semantic_layer_context,
            ),
            text_format=ProviderProposal,
            failure_factory=lambda reason: ProviderFailure(reason=reason),
            failure_with_diagnostic_factory=lambda reason, diagnostic_class: (
                ProviderFailure(
                    reason=reason,
                    diagnostic_class=ProviderFailureDiagnosticClass(diagnostic_class),
                )
            ),
            extra_parse_kwargs={"temperature": 0},
            structured_output_attempts=_STRUCTURED_OUTPUT_ATTEMPTS,
        )


def _build_openai_input(
    *,
    question: str,
    semantic_layer_context: dict[str, object],
) -> list[OpenAIInputMessage]:
    return [
        openai_support.developer_message(_QUESTION_INTERPRETER_DEVELOPER_PROMPT),
        _user_message(
            question=question,
            semantic_layer_context=semantic_layer_context,
        ),
    ]


def _user_message(
    *,
    question: str,
    semantic_layer_context: dict[str, object],
) -> OpenAIInputMessage:
    return {
        "role": "user",
        "content": json.dumps(
            {
                "question": question,
                "semantic_layer_context": semantic_layer_context,
            },
            sort_keys=True,
        ),
    }


def build_openai_question_interpreter_provider(
    environ: collections.abc.Mapping[str, str],
    *,
    client: _OpenAIClient | None = None,
) -> OpenAIQuestionInterpreterProvider:
    """Build the OpenAI provider with env-backed config and SDK client."""
    config = load_openai_question_interpreter_config(environ)
    return OpenAIQuestionInterpreterProvider(
        config=config,
        client=client or openai_support.build_openai_client(config),
    )

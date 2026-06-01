"""OpenAI-backed Question Interpreter provider."""

from __future__ import annotations

import collections.abc
import dataclasses
import functools
import importlib.resources
import json
import typing

from openai import OpenAI

import data_assistant.prompts as prompts
from data_assistant.question_interpreter.proposals import (
    ProviderFailure,
    QuestionFrameProposal,
)

_DEFAULT_OPENAI_MODEL = "gpt-4o-mini"
OpenAIInputMessage: typing.TypeAlias = dict[str, str]
_QUESTION_INTERPRETER_DEVELOPER_PROMPT = "question_interpreter_developer.md"


@dataclasses.dataclass(frozen=True)
class OpenAIQuestionInterpreterConfig:
    """Environment-backed config for the OpenAI Question Interpreter provider."""

    api_key: str
    model: str


class OpenAIQuestionInterpreterConfigError(ValueError):
    """Raised when required OpenAI provider config is missing."""


def load_openai_question_interpreter_config(
    environ: collections.abc.Mapping[str, str],
) -> OpenAIQuestionInterpreterConfig:
    """Load required OpenAI provider config from environment variables."""
    if not environ.get("OPENAI_API_KEY"):
        raise OpenAIQuestionInterpreterConfigError(
            "Missing required OpenAI environment variables: OPENAI_API_KEY"
        )
    return OpenAIQuestionInterpreterConfig(
        api_key=environ["OPENAI_API_KEY"],
        model=environ.get("OPENAI_MODEL", _DEFAULT_OPENAI_MODEL),
    )


class _OpenAIResponsesClient(typing.Protocol):
    def parse(self, **kwargs: object) -> object:
        """Return one structured Responses API result."""


class _OpenAIClient(typing.Protocol):
    responses: _OpenAIResponsesClient


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
    ) -> QuestionFrameProposal | ProviderFailure:
        try:
            response = self._client.responses.parse(
                model=self._config.model,
                input=_build_openai_input(
                    question=question,
                    semantic_layer_context=semantic_layer_context,
                ),
                text_format=QuestionFrameProposal,
                temperature=0,
            )
        except Exception as error:
            return ProviderFailure(reason=str(error) or "OpenAI provider failed")

        refusal = _extract_response_refusal(response)
        if refusal:
            return ProviderFailure(reason=refusal)

        parsed_output = getattr(response, "output_parsed", None)
        if not isinstance(parsed_output, QuestionFrameProposal):
            return ProviderFailure(reason="OpenAI provider returned no parsed output")
        return parsed_output


def _extract_response_refusal(response: object) -> str | None:
    output_items = typing.cast(
        collections.abc.Iterable[object],
        getattr(response, "output", ()),
    )
    for output_item in output_items:
        if getattr(output_item, "type", None) != "message":
            continue
        content_items = typing.cast(
            collections.abc.Iterable[object],
            getattr(output_item, "content", ()),
        )
        for content_item in content_items:
            if getattr(content_item, "type", None) != "refusal":
                continue
            refusal = getattr(content_item, "refusal", None)
            if isinstance(refusal, str) and refusal:
                return refusal
    return None


def _build_openai_input(
    *,
    question: str,
    semantic_layer_context: dict[str, object],
) -> list[OpenAIInputMessage]:
    return [
        _developer_message(),
        _user_message(
            question=question,
            semantic_layer_context=semantic_layer_context,
        ),
    ]


def _developer_message() -> OpenAIInputMessage:
    return {
        "role": "developer",
        "content": _developer_instructions(),
    }


@functools.cache
def _developer_instructions() -> str:
    return (
        importlib.resources.files(prompts)
        .joinpath(_QUESTION_INTERPRETER_DEVELOPER_PROMPT)
        .read_text(encoding="utf-8")
        .strip()
    )


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
        client=client or _build_openai_client(config.api_key),
    )


def _build_openai_client(api_key: str) -> _OpenAIClient:
    return typing.cast(_OpenAIClient, OpenAI(api_key=api_key))

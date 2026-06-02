"""Shared OpenAI plumbing for the Question Interpreter + Reasoning Layer providers.

Both ``question_interpreter.openai_provider`` and
``reasoning_layer.openai_provider`` are thin shells over this module: they keep
their own flat config dataclass, their own ``*ConfigError`` class, their own
``ProviderFailure`` type, and their per-provider input shape / prompt filename /
proposal ``text_format``. Everything else — env parsing, SDK client
construction, refusal extraction, and the structured ``responses.parse`` flow —
lives here so it is written and tested once.

Composition, not inheritance: the reusable logic is parameterized by the
caller's error class, proposal type, ``failure_factory``, and optional extra
``parse(...)`` kwargs (the Question Interpreter passes ``temperature=0``; the
Reasoning Layer passes none).
"""

from __future__ import annotations

import collections.abc
import dataclasses
import functools
import importlib.resources
import typing

from openai import OpenAI

import data_assistant.prompts as prompts

DEFAULT_OPENAI_MODEL = "gpt-4o-mini"
DEFAULT_OPENAI_TIMEOUT_SECONDS = 15.0
DEFAULT_OPENAI_MAX_RETRIES = 1

OpenAIInputMessage: typing.TypeAlias = dict[str, str]

ProposalT = typing.TypeVar("ProposalT")
FailureT = typing.TypeVar("FailureT")


@dataclasses.dataclass(frozen=True)
class _ParseFailure:
    reason: str
    retryable: bool
    diagnostic_class: str


class OpenAIResponsesClient(typing.Protocol):
    def parse(self, **kwargs: object) -> object:
        """Return one structured Responses API result."""


class OpenAIClient(typing.Protocol):
    responses: OpenAIResponsesClient


class OpenAIClientConfig(typing.Protocol):
    """Structural config a component must satisfy to build an SDK client.

    Both ``OpenAIQuestionInterpreterConfig`` and ``OpenAIReasoningConfig``
    satisfy this with their own flat fields — no nested sub-config needed.
    """

    @property
    def api_key(self) -> str: ...

    @property
    def timeout_seconds(self) -> float: ...

    @property
    def max_retries(self) -> int: ...


def require_api_key(
    environ: collections.abc.Mapping[str, str],
    error_factory: collections.abc.Callable[[str], Exception],
) -> str:
    """Return the OpenAI API key or raise the component's config error."""
    api_key = environ.get("OPENAI_API_KEY")
    if not api_key:
        raise error_factory(
            "Missing required OpenAI environment variables: OPENAI_API_KEY"
        )
    return api_key


def parse_timeout_seconds(
    environ: collections.abc.Mapping[str, str],
    error_factory: collections.abc.Callable[[str], Exception],
) -> float:
    """Parse ``OPENAI_TIMEOUT_SECONDS``, defaulting when unset."""
    raw_value = environ.get("OPENAI_TIMEOUT_SECONDS")
    if raw_value is None:
        return DEFAULT_OPENAI_TIMEOUT_SECONDS
    try:
        return float(raw_value)
    except ValueError as error:
        raise error_factory(f"Invalid OPENAI_TIMEOUT_SECONDS: {raw_value!r}") from error


def parse_max_retries(
    environ: collections.abc.Mapping[str, str],
    error_factory: collections.abc.Callable[[str], Exception],
) -> int:
    """Parse ``OPENAI_MAX_RETRIES``, defaulting when unset."""
    raw_value = environ.get("OPENAI_MAX_RETRIES")
    if raw_value is None:
        return DEFAULT_OPENAI_MAX_RETRIES
    try:
        return int(raw_value)
    except ValueError as error:
        raise error_factory(f"Invalid OPENAI_MAX_RETRIES: {raw_value!r}") from error


def build_openai_client(config: OpenAIClientConfig) -> OpenAIClient:
    """Construct an OpenAI SDK client from any structural client config."""
    return typing.cast(
        OpenAIClient,
        OpenAI(
            api_key=config.api_key,
            timeout=config.timeout_seconds,
            max_retries=config.max_retries,
        ),
    )


def run_parse(
    *,
    client: OpenAIClient,
    model: str,
    input_messages: list[OpenAIInputMessage],
    text_format: type[ProposalT],
    failure_factory: collections.abc.Callable[[str], FailureT],
    failure_with_diagnostic_factory: (
        collections.abc.Callable[[str, str], FailureT] | None
    ) = None,
    extra_parse_kwargs: dict[str, object] | None = None,
    structured_output_attempts: int = 1,
) -> ProposalT | FailureT:
    """Run structured ``responses.parse`` and normalize the outcome.

    Centralizes the parse → exception → refusal → missing-output flow shared by
    both providers. ``extra_parse_kwargs`` lets a caller forward additional
    keyword arguments to ``parse`` (the Question Interpreter passes
    ``temperature=0``; the Reasoning Layer passes none). Callers may opt into
    an extra structured-output attempt for retryable parse failures while
    refusals still return immediately.
    """
    if structured_output_attempts < 1:
        raise ValueError("structured_output_attempts must be at least 1")
    last_failure: _ParseFailure | None = None
    seen_diagnostic_classes: set[str] = set()
    for _ in range(structured_output_attempts):
        result = _run_parse_once(
            client=client,
            model=model,
            input_messages=input_messages,
            text_format=text_format,
            extra_parse_kwargs=extra_parse_kwargs,
        )
        if not isinstance(result, _ParseFailure):
            return result
        if not result.retryable:
            return _build_failure(
                reason=result.reason,
                diagnostic_class=result.diagnostic_class,
                failure_factory=failure_factory,
                failure_with_diagnostic_factory=failure_with_diagnostic_factory,
            )
        last_failure = result
        seen_diagnostic_classes.add(result.diagnostic_class)

    if last_failure is None:
        raise AssertionError("structured output attempt loop must run at least once")
    if structured_output_attempts == 1:
        return _build_failure(
            reason=last_failure.reason,
            diagnostic_class=last_failure.diagnostic_class,
            failure_factory=failure_factory,
            failure_with_diagnostic_factory=failure_with_diagnostic_factory,
        )
    exhausted_diagnostic_class = (
        "structured_output_retry_exhausted"
        if last_failure.diagnostic_class == "missing_parsed_output"
        or len(seen_diagnostic_classes) > 1
        else last_failure.diagnostic_class
    )
    return _build_failure(
        reason=(
            "OpenAI provider failed after "
            f"{structured_output_attempts} structured output attempts: "
            f"{last_failure.reason}"
        ),
        diagnostic_class=exhausted_diagnostic_class,
        failure_factory=failure_factory,
        failure_with_diagnostic_factory=failure_with_diagnostic_factory,
    )


def _run_parse_once(
    *,
    client: OpenAIClient,
    model: str,
    input_messages: list[OpenAIInputMessage],
    text_format: type[ProposalT],
    extra_parse_kwargs: dict[str, object] | None,
) -> ProposalT | _ParseFailure:
    try:
        response = client.responses.parse(
            model=model,
            input=input_messages,
            text_format=text_format,
            **(extra_parse_kwargs or {}),
        )
    except Exception as error:
        return _ParseFailure(
            reason=str(error) or "OpenAI provider failed",
            retryable=True,
            diagnostic_class="provider_exception",
        )

    refusal = extract_response_refusal(response)
    if refusal:
        return _ParseFailure(
            reason=refusal,
            retryable=False,
            diagnostic_class="provider_refusal",
        )

    parsed_output = getattr(response, "output_parsed", None)
    if not isinstance(parsed_output, text_format):
        return _ParseFailure(
            reason="OpenAI provider returned no parsed output",
            retryable=True,
            diagnostic_class="missing_parsed_output",
        )
    return parsed_output


def _build_failure(
    *,
    reason: str,
    diagnostic_class: str,
    failure_factory: collections.abc.Callable[[str], FailureT],
    failure_with_diagnostic_factory: (
        collections.abc.Callable[[str, str], FailureT] | None
    ),
) -> FailureT:
    if failure_with_diagnostic_factory is None:
        return failure_factory(reason)
    return failure_with_diagnostic_factory(reason, diagnostic_class)


def extract_response_refusal(response: object) -> str | None:
    """Return the first refusal string in a Responses result, if any."""
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


def developer_message(prompt_filename: str) -> OpenAIInputMessage:
    """Build the developer-role message for a component's prompt file."""
    return {
        "role": "developer",
        "content": _developer_instructions(prompt_filename),
    }


@functools.cache
def _developer_instructions(prompt_filename: str) -> str:
    return (
        importlib.resources.files(prompts)
        .joinpath(prompt_filename)
        .read_text(encoding="utf-8")
        .strip()
    )

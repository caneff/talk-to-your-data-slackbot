import collections.abc
import json
import typing

import pytest

import data_assistant.openai_support as openai_support
import data_assistant.question_interpreter as question_interpreter
import data_assistant.question_interpreter.openai_provider as openai_provider
import data_assistant.question_interpreter.testing_support as test_support


def test_load_openai_provider_config_requires_api_key_only_when_selected() -> None:
    with pytest.raises(
        question_interpreter.OpenAIQuestionInterpreterConfigError
    ) as error_info:
        question_interpreter.load_openai_question_interpreter_config({})

    assert str(error_info.value) == (
        "Missing required OpenAI environment variables: OPENAI_API_KEY"
    )


def test_load_openai_provider_config_allows_model_override() -> None:
    override_config = question_interpreter.load_openai_question_interpreter_config(
        {
            "OPENAI_API_KEY": "test-key",
            "OPENAI_MODEL": "gpt-test-mini",
        }
    )

    assert override_config == (
        question_interpreter.OpenAIQuestionInterpreterConfig(
            api_key="test-key",
            model="gpt-test-mini",
        )
    )


def test_load_openai_provider_config_defaults_timeout_and_retries() -> None:
    config = question_interpreter.load_openai_question_interpreter_config(
        {"OPENAI_API_KEY": "test-key"}
    )

    assert config.timeout_seconds == 15.0
    assert config.max_retries == 1


def test_load_openai_provider_config_allows_timeout_and_retries_override() -> None:
    config = question_interpreter.load_openai_question_interpreter_config(
        {
            "OPENAI_API_KEY": "test-key",
            "OPENAI_TIMEOUT_SECONDS": "42.5",
            "OPENAI_MAX_RETRIES": "3",
        }
    )

    assert config.timeout_seconds == 42.5
    assert config.max_retries == 3


def test_load_openai_provider_config_rejects_non_numeric_timeout() -> None:
    with pytest.raises(
        question_interpreter.OpenAIQuestionInterpreterConfigError
    ) as error_info:
        question_interpreter.load_openai_question_interpreter_config(
            {"OPENAI_API_KEY": "test-key", "OPENAI_TIMEOUT_SECONDS": "soon"}
        )

    assert "OPENAI_TIMEOUT_SECONDS" in str(error_info.value)


def test_load_openai_provider_config_rejects_non_numeric_retries() -> None:
    with pytest.raises(
        question_interpreter.OpenAIQuestionInterpreterConfigError
    ) as error_info:
        question_interpreter.load_openai_question_interpreter_config(
            {"OPENAI_API_KEY": "test-key", "OPENAI_MAX_RETRIES": "lots"}
        )

    assert "OPENAI_MAX_RETRIES" in str(error_info.value)


def test_build_openai_provider_passes_timeout_and_retries_to_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_kwargs: dict[str, object] = {}

    class FakeOpenAI:
        def __init__(self, **kwargs: object) -> None:
            captured_kwargs.update(kwargs)

        responses = object()

    monkeypatch.setattr(openai_support, "OpenAI", FakeOpenAI)

    question_interpreter.build_openai_question_interpreter_provider(
        {
            "OPENAI_API_KEY": "test-key",
            "OPENAI_TIMEOUT_SECONDS": "42.5",
            "OPENAI_MAX_RETRIES": "3",
        }
    )

    assert captured_kwargs["api_key"] == "test-key"
    assert captured_kwargs["timeout"] == 42.5
    assert captured_kwargs["max_retries"] == 3


def _openai_provider_returning(
    response: object,
    *,
    parse_calls: list[dict[str, object]] | None = None,
) -> question_interpreter.OpenAIQuestionInterpreterProvider:
    """Build a provider with a fake Responses client.

    Parameters
    ----------
    response : object
        Response object returned by the fake `responses.parse` call.
    parse_calls : list[dict[str, object]] | None, optional
        Optional sink for captured `responses.parse` keyword arguments.

    Returns
    -------
    question_interpreter.OpenAIQuestionInterpreterProvider
        Provider wired to the fake OpenAI client.
    """

    class FakeResponsesClient:
        def parse(self, **kwargs: object) -> object:
            if parse_calls is not None:
                parse_calls.append(kwargs)
            return response

    class FakeOpenAIClient:
        responses = FakeResponsesClient()

    return question_interpreter.OpenAIQuestionInterpreterProvider(
        config=question_interpreter.OpenAIQuestionInterpreterConfig(
            api_key="test-key",
            model="gpt-test-mini",
        ),
        client=typing.cast(
            openai_provider._OpenAIClient,  # pyright: ignore[reportPrivateUsage]
            FakeOpenAIClient(),
        ),
    )


def _openai_provider_returning_results(
    results: collections.abc.Sequence[object | Exception],
    *,
    parse_calls: list[dict[str, object]] | None = None,
) -> question_interpreter.OpenAIQuestionInterpreterProvider:
    call_index = 0

    class FakeResponsesClient:
        def parse(self, **kwargs: object) -> object:
            nonlocal call_index
            if parse_calls is not None:
                parse_calls.append(kwargs)
            result = results[call_index]
            call_index += 1
            if isinstance(result, Exception):
                raise result
            return result

    class FakeOpenAIClient:
        responses = FakeResponsesClient()

    return question_interpreter.OpenAIQuestionInterpreterProvider(
        config=question_interpreter.OpenAIQuestionInterpreterConfig(
            api_key="test-key",
            model="gpt-test-mini",
        ),
        client=typing.cast(
            openai_provider._OpenAIClient,  # pyright: ignore[reportPrivateUsage]
            FakeOpenAIClient(),
        ),
    )


def test_build_openai_provider_accepts_injected_client() -> None:
    class FakeResponsesClient:
        def parse(self, **kwargs: object) -> object:
            assert kwargs["model"] == "gpt-test-mini"
            return FakeParsedResponse()

    class FakeParsedResponse:
        output_parsed = test_support.question_frame_proposal()

    class FakeOpenAIClient:
        responses = FakeResponsesClient()

    client = typing.cast(
        openai_provider._OpenAIClient,  # pyright: ignore[reportPrivateUsage]
        FakeOpenAIClient(),
    )

    provider = question_interpreter.build_openai_question_interpreter_provider(
        {"OPENAI_API_KEY": "test-key", "OPENAI_MODEL": "gpt-test-mini"},
        client=client,
    )

    result = provider.propose_question_frame(
        question=test_support.CANONICAL_DATA_QUESTION,
        semantic_layer_context={"datasets": []},
    )
    assert result == FakeParsedResponse.output_parsed


def test_openai_provider_returns_question_frame_proposal_from_parsed_response() -> None:
    parse_calls: list[dict[str, object]] = []

    class FakeParsedResponse:
        output_parsed = test_support.question_frame_proposal()

    provider = _openai_provider_returning(
        FakeParsedResponse(),
        parse_calls=parse_calls,
    )
    question = "sentinel question"
    semantic_layer_context: dict[str, object] = {"sentinel": "context"}

    result = provider.propose_question_frame(
        question=question,
        semantic_layer_context=semantic_layer_context,
    )

    assert result == FakeParsedResponse.output_parsed
    assert len(parse_calls) == 1
    assert parse_calls[0]["temperature"] == 0
    input_messages = typing.cast(
        list[dict[str, str]],
        parse_calls[0]["input"],
    )
    user_payload = json.loads(input_messages[1]["content"])
    assert user_payload["question"] == question
    assert user_payload["semantic_layer_context"] == semantic_layer_context
    assert "prompt_context" not in user_payload


def test_openai_provider_clears_ambiguity_when_unknown_metric_is_reported() -> None:
    class FakeParsedResponse:
        output_parsed = question_interpreter.ProviderProposal(
            intent="summarize",
            metric=None,
            metric_ambiguity="average order value",
            unknown_metric="average order value",
            field_operations=(
                question_interpreter.ProviderFieldOperation(
                    operation="range_filter",
                    field="order date",
                    lower="2026-01-01",
                    upper="2026-01-31",
                ),
            ),
        )

    provider = _openai_provider_returning(FakeParsedResponse())

    result = provider.propose_question_frame(
        question="What was our average order value in January 2026?",
        semantic_layer_context={"datasets": []},
    )

    assert result == FakeParsedResponse.output_parsed.model_copy(
        update={"metric_ambiguity": None}
    )


def test_openai_provider_strips_vacuous_field_operations() -> None:
    class FakeParsedResponse:
        output_parsed = question_interpreter.ProviderProposal(
            intent="summarize",
            metric="revenue",
            field_operations=(
                question_interpreter.ProviderFieldOperation(
                    operation="group_by",
                    field="order channel",
                ),
                question_interpreter.ProviderFieldOperation(
                    operation="range_filter",
                    field="order date",
                    lower=None,
                    upper=None,
                ),
                question_interpreter.ProviderFieldOperation(
                    operation="include_filter",
                    field="store region",
                    values=(),
                ),
                question_interpreter.ProviderFieldOperation(
                    operation="range_filter",
                    field="ship date",
                    lower="2026-01-01",
                    upper="2026-01-31",
                ),
                question_interpreter.ProviderFieldOperation(
                    operation="exclude_filter",
                    field="product category",
                    values=(),
                ),
            ),
        )

    provider = _openai_provider_returning(FakeParsedResponse())

    result = provider.propose_question_frame(
        question="Show revenue by order channel for shipped orders in January 2026.",
        semantic_layer_context={"datasets": []},
    )

    assert result == FakeParsedResponse.output_parsed.model_copy(
        update={
            "field_operations": (
                question_interpreter.ProviderFieldOperation(
                    operation="group_by",
                    field="order channel",
                ),
                question_interpreter.ProviderFieldOperation(
                    operation="range_filter",
                    field="ship date",
                    lower="2026-01-01",
                    upper="2026-01-31",
                ),
            )
        }
    )


def test_openai_provider_keeps_relative_range_filter_with_null_bounds() -> None:
    # A source="relative" range_filter carries unit+count and has null bounds by
    # design (ADR-0026); canonicalization must NOT strip it as vacuous, or the
    # interpreter never sees the relative window and the question loses its time
    # filter. Regression for the empty-field_operations live-eval failure.
    relative_operation = question_interpreter.ProviderFieldOperation(
        operation="range_filter",
        field="order date",
        source="relative",
        lower=None,
        upper=None,
        unit="quarter",
        count=1,
    )

    class FakeParsedResponse:
        output_parsed = question_interpreter.ProviderProposal(
            intent="summarize",
            metric="total net revenue",
            field_operations=(relative_operation,),
        )

    provider = _openai_provider_returning(FakeParsedResponse())

    result = provider.propose_question_frame(
        question="What was total net revenue last quarter?",
        semantic_layer_context={"datasets": []},
    )

    assert isinstance(result, question_interpreter.ProviderProposal)
    assert result.field_operations == (relative_operation,)


def test_openai_provider_schema_avoids_union_items_for_field_operations() -> None:
    response_schema = question_interpreter.ProviderProposal.model_json_schema()
    field_operations_schema = response_schema["properties"]["field_operations"]

    assert "oneOf" not in json.dumps(field_operations_schema)


def test_openai_provider_schema_guides_supported_summary_intent() -> None:
    response_schema = question_interpreter.ProviderProposal.model_json_schema()
    intent_schema = response_schema["properties"]["intent"]

    assert "Use summarize" in intent_schema["description"]
    assert "catalog_discovery" in intent_schema["description"]
    assert "what was" in intent_schema["description"]
    assert "show" in intent_schema["description"]


def test_openai_provider_schema_rejects_empty_implicit_filters() -> None:
    response_schema = question_interpreter.ProviderProposal.model_json_schema()
    field_operation_schema = response_schema["$defs"]["ProviderFieldOperation"]
    field_operations_schema = response_schema["properties"]["field_operations"]
    operation_schema = field_operation_schema["properties"]["operation"]
    values_schema = field_operation_schema["properties"]["values"]

    assert "merely available in context" in field_operations_schema["description"]
    assert (
        "question omits time, omit date operations"
        in (field_operations_schema["description"])
    )
    assert (
        "merely available in semantic_layer_context" in operation_schema["description"]
    )
    assert "explicitly included dimension values" in operation_schema["description"]
    assert (
        "Non-empty explicit date or dimension values" in (values_schema["description"])
    )
    assert "date or dimension values" in values_schema["description"]
    assert (
        "never emit include_filter or exclude_filter with empty values"
        in (values_schema["description"])
    )


# Developer-prompt wiring guards.
#
# These guard the two regressions a unit test can actually catch: the prompt
# stops being wired into the call, or the file is truncated so a whole section
# vanishes. They do NOT pin prose — content equality is checked against the file
# itself, so rewording the guidance never false-fails. Whether the model obeys
# the guidance (classifies rank, picks one date field, etc.) is a behavioral
# question, guarded only by the manual Live Provider Proposal Eval run before
# shipping a prompt change. Do not re-add substring pins on guidance sentences:
# they break on rephrase and guard nothing the live eval doesn't already cover.
def _captured_input_messages() -> list[dict[str, str]]:
    """Return the input messages the provider sends for a canonical question."""
    parse_calls: list[dict[str, object]] = []

    class FakeParsedResponse:
        output_parsed = test_support.question_frame_proposal()

    provider = _openai_provider_returning(
        FakeParsedResponse(),
        parse_calls=parse_calls,
    )
    provider.propose_question_frame(
        question=test_support.CANONICAL_DATA_QUESTION,
        semantic_layer_context={"datasets": []},
    )
    return typing.cast(list[dict[str, str]], parse_calls[0]["input"])


def test_provider_wires_developer_prompt_file_as_first_message() -> None:
    """The provider sends the developer-prompt file, verbatim, as message[0].

    Compared against the file via developer_message, so this tracks any prompt
    edit instead of pinning its wording.
    """
    developer_message = _captured_input_messages()[0]
    expected = openai_support.developer_message(
        openai_provider._QUESTION_INTERPRETER_DEVELOPER_PROMPT  # pyright: ignore[reportPrivateUsage]
    )
    assert developer_message["role"] == "developer"
    assert developer_message["content"] == expected["content"]
    assert developer_message["content"].strip() != ""


def test_developer_prompt_retains_all_sections() -> None:
    """Truncation tripwire: every structural section header survives.

    Headers are stable structure, not guidance prose, so this catches a gutted
    or truncated prompt without breaking when wording changes.
    """
    developer_prompt = _captured_input_messages()[0]["content"]
    for header in (
        "## Intent",
        "## Metric and ambiguity",
        "## Field operations",
        "## Dates",
        "## Examples",
    ):
        assert header in developer_prompt


def test_openai_provider_maps_refusal_to_provider_failure() -> None:
    parse_calls: list[dict[str, object]] = []

    class FakeRefusalContent:
        type = "refusal"
        refusal = "cannot comply"

    class FakeMessageOutput:
        type = "message"
        content = [FakeRefusalContent()]

    class FakeRefusalResponse:
        output_parsed = None
        output = [FakeMessageOutput()]

    provider = _openai_provider_returning(
        FakeRefusalResponse(),
        parse_calls=parse_calls,
    )

    result = provider.propose_question_frame(
        question=test_support.CANONICAL_DATA_QUESTION,
        semantic_layer_context={"datasets": []},
    )

    assert result == question_interpreter.ProviderFailure(
        reason="cannot comply",
        diagnostic_class=(
            question_interpreter.ProviderFailureDiagnosticClass.PROVIDER_REFUSAL
        ),
    )
    assert len(parse_calls) == 1


def test_openai_provider_retries_parse_exception_once() -> None:
    parse_calls: list[dict[str, object]] = []

    class FakeParsedResponse:
        output_parsed = test_support.question_frame_proposal()

    provider = _openai_provider_returning_results(
        (
            ValueError("Invalid JSON: EOF while parsing a value"),
            FakeParsedResponse(),
        ),
        parse_calls=parse_calls,
    )

    result = provider.propose_question_frame(
        question=test_support.CANONICAL_DATA_QUESTION,
        semantic_layer_context={"datasets": []},
    )

    assert result == FakeParsedResponse.output_parsed
    assert len(parse_calls) == 2


def test_openai_provider_retries_missing_parsed_output_once() -> None:
    parse_calls: list[dict[str, object]] = []

    class FakeMissingParsedResponse:
        output_parsed = None

    class FakeParsedResponse:
        output_parsed = test_support.question_frame_proposal()

    provider = _openai_provider_returning_results(
        (FakeMissingParsedResponse(), FakeParsedResponse()),
        parse_calls=parse_calls,
    )

    result = provider.propose_question_frame(
        question=test_support.CANONICAL_DATA_QUESTION,
        semantic_layer_context={"datasets": []},
    )

    assert result == FakeParsedResponse.output_parsed
    assert len(parse_calls) == 2


def test_openai_provider_maps_exhausted_structured_output_attempts_to_failure() -> None:
    parse_calls: list[dict[str, object]] = []

    class FakeMissingParsedResponse:
        output_parsed = None

    provider = _openai_provider_returning_results(
        (FakeMissingParsedResponse(), FakeMissingParsedResponse()),
        parse_calls=parse_calls,
    )

    result = provider.propose_question_frame(
        question=test_support.CANONICAL_DATA_QUESTION,
        semantic_layer_context={"datasets": []},
    )

    assert result == question_interpreter.ProviderFailure(
        reason=(
            "OpenAI provider failed after 2 structured output attempts: "
            "OpenAI provider returned no parsed output"
        ),
        diagnostic_class=(
            question_interpreter.ProviderFailureDiagnosticClass.STRUCTURED_OUTPUT_RETRY_EXHAUSTED
        ),
    )
    assert len(parse_calls) == 2


def test_openai_provider_maps_parse_exception_to_provider_failure_diagnostic() -> None:
    parse_calls: list[dict[str, object]] = []

    provider = _openai_provider_returning_results(
        (
            RuntimeError("boom"),
            RuntimeError("boom"),
        ),
        parse_calls=parse_calls,
    )

    result = provider.propose_question_frame(
        question=test_support.CANONICAL_DATA_QUESTION,
        semantic_layer_context={"datasets": []},
    )

    assert result == question_interpreter.ProviderFailure(
        reason="OpenAI provider failed after 2 structured output attempts: boom",
        diagnostic_class=(
            question_interpreter.ProviderFailureDiagnosticClass.PROVIDER_EXCEPTION
        ),
    )
    assert len(parse_calls) == 2


def test_openai_provider_maps_mixed_retryable_failures_to_retry_exhausted() -> None:
    parse_calls: list[dict[str, object]] = []

    class FakeMissingParsedResponse:
        output_parsed = None

    provider = _openai_provider_returning_results(
        (
            RuntimeError("boom"),
            FakeMissingParsedResponse(),
        ),
        parse_calls=parse_calls,
    )

    result = provider.propose_question_frame(
        question=test_support.CANONICAL_DATA_QUESTION,
        semantic_layer_context={"datasets": []},
    )

    assert result == question_interpreter.ProviderFailure(
        reason=(
            "OpenAI provider failed after 2 structured output attempts: "
            "OpenAI provider returned no parsed output"
        ),
        diagnostic_class=(
            question_interpreter.ProviderFailureDiagnosticClass.STRUCTURED_OUTPUT_RETRY_EXHAUSTED
        ),
    )
    assert len(parse_calls) == 2

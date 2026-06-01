import json
import typing

import pytest

import data_assistant.reasoning_layer as reasoning_layer
import data_assistant.reasoning_layer.openai_provider as openai_provider
import data_assistant.reasoning_layer.test_support as test_support


def test_load_openai_reasoning_config_requires_api_key() -> None:
    with pytest.raises(reasoning_layer.OpenAIReasoningConfigError) as error_info:
        reasoning_layer.load_openai_reasoning_config({})

    assert str(error_info.value) == (
        "Missing required OpenAI environment variables: OPENAI_API_KEY"
    )


def test_load_openai_reasoning_config_allows_model_override() -> None:
    override_config = reasoning_layer.load_openai_reasoning_config(
        {
            "OPENAI_API_KEY": "test-key",
            "OPENAI_MODEL": "gpt-test-mini",
        }
    )

    assert override_config == (
        reasoning_layer.OpenAIReasoningConfig(
            api_key="test-key",
            model="gpt-test-mini",
        )
    )


def _openai_provider_returning(
    response: object,
    *,
    parse_calls: list[dict[str, object]] | None = None,
) -> reasoning_layer.OpenAIReasoningProvider:
    """Build a provider with a fake Responses client.

    Parameters
    ----------
    response : object
        Response object returned by the fake `responses.parse` call.
    parse_calls : list[dict[str, object]] | None, optional
        Optional sink for captured `responses.parse` keyword arguments.

    Returns
    -------
    reasoning_layer.OpenAIReasoningProvider
        Provider wired to the fake OpenAI client.
    """

    class FakeResponsesClient:
        def parse(self, **kwargs: object) -> object:
            if parse_calls is not None:
                parse_calls.append(kwargs)
            return response

    class FakeOpenAIClient:
        responses = FakeResponsesClient()

    return reasoning_layer.OpenAIReasoningProvider(
        config=reasoning_layer.OpenAIReasoningConfig(
            api_key="test-key",
            model="gpt-test-mini",
        ),
        client=typing.cast(
            openai_provider._OpenAIClient,  # pyright: ignore[reportPrivateUsage]
            FakeOpenAIClient(),
        ),
    )


def test_build_openai_reasoning_provider_accepts_injected_client() -> None:
    class FakeResponsesClient:
        def parse(self, **kwargs: object) -> object:
            assert kwargs["model"] == "gpt-test-mini"
            return FakeParsedResponse()

    class FakeParsedResponse:
        output_parsed = test_support.narrative_proposal()

    class FakeOpenAIClient:
        responses = FakeResponsesClient()

    client = typing.cast(
        openai_provider._OpenAIClient,  # pyright: ignore[reportPrivateUsage]
        FakeOpenAIClient(),
    )

    provider = reasoning_layer.build_openai_reasoning_provider(
        {"OPENAI_API_KEY": "test-key", "OPENAI_MODEL": "gpt-test-mini"},
        client=client,
    )

    result = provider.propose_narrative(result_shape={"metric": "Total revenue"})
    assert result == FakeParsedResponse.output_parsed


def test_openai_provider_returns_narrative_proposal_from_parsed_response() -> None:
    parse_calls: list[dict[str, object]] = []

    class FakeParsedResponse:
        output_parsed = test_support.narrative_proposal()

    provider = _openai_provider_returning(
        FakeParsedResponse(),
        parse_calls=parse_calls,
    )
    result_shape: dict[str, object] = {
        "metric": "Total revenue",
        "time_range": "2026-01-01 through 2026-01-31",
        "dimension": "regions",
        "dimension_count": 5,
        "top_dimension": "West",
    }

    result = provider.propose_narrative(result_shape=result_shape)

    assert result == FakeParsedResponse.output_parsed
    assert len(parse_calls) == 1
    input_messages = typing.cast(
        list[dict[str, str]],
        parse_calls[0]["input"],
    )
    user_payload = json.loads(input_messages[1]["content"])
    assert user_payload == {"result_shape": result_shape}
    assert "question" not in user_payload


def test_openai_provider_maps_refusal_to_provider_failure() -> None:
    class FakeRefusalContent:
        type = "refusal"
        refusal = "cannot comply"

    class FakeMessageOutput:
        type = "message"
        content = [FakeRefusalContent()]

    class FakeRefusalResponse:
        output_parsed = None
        output = [FakeMessageOutput()]

    provider = _openai_provider_returning(FakeRefusalResponse())

    result = provider.propose_narrative(result_shape={"metric": "Total revenue"})

    assert result == reasoning_layer.ProviderFailure(reason="cannot comply")


def test_openai_provider_maps_missing_parsed_output_to_provider_failure() -> None:
    class FakeMissingParsedResponse:
        output_parsed = None

    provider = _openai_provider_returning(FakeMissingParsedResponse())

    result = provider.propose_narrative(result_shape={"metric": "Total revenue"})

    assert result == reasoning_layer.ProviderFailure(
        reason="OpenAI provider returned no parsed output"
    )


def test_openai_provider_maps_call_error_to_provider_failure() -> None:
    class FailingResponsesClient:
        def parse(self, **kwargs: object) -> object:
            del kwargs
            raise RuntimeError("boom")

    class FakeOpenAIClient:
        responses = FailingResponsesClient()

    provider = reasoning_layer.OpenAIReasoningProvider(
        config=reasoning_layer.OpenAIReasoningConfig(
            api_key="test-key",
            model="gpt-test-mini",
        ),
        client=typing.cast(
            openai_provider._OpenAIClient,  # pyright: ignore[reportPrivateUsage]
            FakeOpenAIClient(),
        ),
    )

    result = provider.propose_narrative(result_shape={"metric": "Total revenue"})

    assert result == reasoning_layer.ProviderFailure(reason="boom")


def test_openai_provider_developer_prompt_lists_slots_and_forbids_digits() -> None:
    parse_calls: list[dict[str, object]] = []

    class FakeParsedResponse:
        output_parsed = test_support.narrative_proposal()

    provider = _openai_provider_returning(
        FakeParsedResponse(),
        parse_calls=parse_calls,
    )

    provider.propose_narrative(result_shape={"metric": "Total revenue"})

    input_messages = typing.cast(
        list[dict[str, str]],
        parse_calls[0]["input"],
    )
    developer_prompt = input_messages[0]["content"]
    for slot_name in (
        "{metric}",
        "{time_range}",
        "{metric_total}",
        "{dimension}",
        "{dimension_count}",
        "{top_dimension}",
        "{top_value}",
    ):
        assert slot_name in developer_prompt
    assert "never write a literal digit" in developer_prompt.lower()
    assert "Do not place aggregate words" in developer_prompt
    assert '"total", "sum", or "count"' in developer_prompt
    assert "metric slot already contains the business metric name" in developer_prompt

import datetime
import json
import typing

import pytest

import data_assistant.llm_question_interpreter as llm_question_interpreter
import data_assistant.question_interpreter_test_support as interpreter_support


def test_load_openai_provider_config_requires_api_key_only_when_selected() -> None:
    with pytest.raises(
        llm_question_interpreter.OpenAIQuestionInterpreterConfigError
    ) as error_info:
        llm_question_interpreter.load_openai_question_interpreter_config({})

    assert str(error_info.value) == (
        "Missing required OpenAI environment variables: OPENAI_API_KEY"
    )


def test_load_openai_provider_config_uses_default_model_and_allows_override() -> None:
    default_config = llm_question_interpreter.load_openai_question_interpreter_config(
        {"OPENAI_API_KEY": "test-key"}
    )
    override_config = llm_question_interpreter.load_openai_question_interpreter_config(
        {
            "OPENAI_API_KEY": "test-key",
            "OPENAI_MODEL": "gpt-test-mini",
        }
    )

    assert default_config == llm_question_interpreter.OpenAIQuestionInterpreterConfig(
        api_key="test-key",
        model="gpt-4o-mini",
    )
    assert override_config == (
        llm_question_interpreter.OpenAIQuestionInterpreterConfig(
            api_key="test-key",
            model="gpt-test-mini",
        )
    )


def test_build_openai_provider_accepts_injected_client() -> None:
    class FakeResponsesClient:
        def parse(self, **kwargs: object) -> object:
            assert kwargs["model"] == "gpt-test-mini"
            return FakeParsedResponse()

    class FakeParsedResponse:
        output_parsed = interpreter_support.question_frame_proposal()

    class FakeOpenAIClient:
        responses = FakeResponsesClient()

    client = typing.cast(
        llm_question_interpreter._OpenAIClient,  # pyright: ignore[reportPrivateUsage]
        FakeOpenAIClient(),
    )

    provider = llm_question_interpreter.build_openai_question_interpreter_provider(
        {"OPENAI_API_KEY": "test-key", "OPENAI_MODEL": "gpt-test-mini"},
        client=client,
    )

    result = provider.propose_question_frame(
        question=interpreter_support.CANONICAL_DATA_QUESTION,
        semantic_layer_context={"datasets": []},
    )
    assert result == FakeParsedResponse.output_parsed


def test_openai_provider_returns_question_frame_proposal_from_parsed_response() -> None:
    parse_calls: list[dict[str, object]] = []

    class FakeParsedResponse:
        output_parsed = llm_question_interpreter.QuestionFrameProposal(
            intent="summarize",
            metric="total revenue",
            dimension="region",
            time_range=llm_question_interpreter.TimeRangeProposal(
                label="January 2026",
                start_date=datetime.date(2026, 1, 1),
                end_date=datetime.date(2026, 1, 31),
            ),
            filters=(),
        )

    class FakeResponsesClient:
        def parse(self, **kwargs: object) -> FakeParsedResponse:
            parse_calls.append(kwargs)
            return FakeParsedResponse()

    class FakeOpenAIClient:
        responses = FakeResponsesClient()

    provider = llm_question_interpreter.OpenAIQuestionInterpreterProvider(
        config=llm_question_interpreter.OpenAIQuestionInterpreterConfig(
            api_key="test-key",
            model="gpt-test-mini",
        ),
        client=typing.cast(
            llm_question_interpreter._OpenAIClient,  # pyright: ignore[reportPrivateUsage]
            FakeOpenAIClient(),
        ),
    )

    result = provider.propose_question_frame(
        question=interpreter_support.CANONICAL_DATA_QUESTION,
        semantic_layer_context={
            "all_metric_labels": ["total revenue"],
            "all_dimension_labels": ["region"],
            "supported_intents": ["summarize"],
            "datasets": [],
        },
    )

    assert result == FakeParsedResponse.output_parsed
    assert len(parse_calls) == 1
    assert parse_calls[0]["model"] == "gpt-test-mini"
    assert parse_calls[0]["text_format"] is (
        llm_question_interpreter.QuestionFrameProposal
    )
    input_messages = typing.cast(
        list[dict[str, str]],
        parse_calls[0]["input"],
    )
    assert [message["role"] for message in input_messages] == ["developer", "user"]
    assert input_messages[0]["content"] == (
        llm_question_interpreter._developer_instructions()  # pyright: ignore[reportPrivateUsage]
    )
    user_payload = json.loads(input_messages[1]["content"])
    assert user_payload == {
        "question": interpreter_support.CANONICAL_DATA_QUESTION,
        "semantic_layer_context": {
            "all_metric_labels": ["total revenue"],
            "all_dimension_labels": ["region"],
            "supported_intents": ["summarize"],
            "datasets": [],
        },
    }
    assert "prompt_context" not in user_payload


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

    class FakeResponsesClient:
        def parse(self, **kwargs: object) -> FakeRefusalResponse:
            del kwargs
            return FakeRefusalResponse()

    class FakeOpenAIClient:
        responses = FakeResponsesClient()

    provider = llm_question_interpreter.OpenAIQuestionInterpreterProvider(
        config=llm_question_interpreter.OpenAIQuestionInterpreterConfig(
            api_key="test-key",
            model="gpt-test-mini",
        ),
        client=typing.cast(
            llm_question_interpreter._OpenAIClient,  # pyright: ignore[reportPrivateUsage]
            FakeOpenAIClient(),
        ),
    )

    result = provider.propose_question_frame(
        question=interpreter_support.CANONICAL_DATA_QUESTION,
        semantic_layer_context={"datasets": []},
    )

    assert result == llm_question_interpreter.ProviderFailure(reason="cannot comply")


def test_openai_provider_maps_missing_parsed_output_to_provider_failure() -> None:
    class FakeMissingParsedResponse:
        output_parsed = None

    class FakeResponsesClient:
        def parse(self, **kwargs: object) -> FakeMissingParsedResponse:
            del kwargs
            return FakeMissingParsedResponse()

    class FakeOpenAIClient:
        responses = FakeResponsesClient()

    provider = llm_question_interpreter.OpenAIQuestionInterpreterProvider(
        config=llm_question_interpreter.OpenAIQuestionInterpreterConfig(
            api_key="test-key",
            model="gpt-test-mini",
        ),
        client=typing.cast(
            llm_question_interpreter._OpenAIClient,  # pyright: ignore[reportPrivateUsage]
            FakeOpenAIClient(),
        ),
    )

    result = provider.propose_question_frame(
        question=interpreter_support.CANONICAL_DATA_QUESTION,
        semantic_layer_context={"datasets": []},
    )

    assert result == llm_question_interpreter.ProviderFailure(
        reason="OpenAI provider returned no parsed output"
    )

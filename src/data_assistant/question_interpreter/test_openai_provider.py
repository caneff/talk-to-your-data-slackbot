import json
import typing

import pytest

import data_assistant.question_interpreter as question_interpreter
import data_assistant.question_interpreter.openai_provider as openai_provider
import data_assistant.question_interpreter.test_support as test_support


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
    input_messages = typing.cast(
        list[dict[str, str]],
        parse_calls[0]["input"],
    )
    user_payload = json.loads(input_messages[1]["content"])
    assert user_payload["question"] == question
    assert user_payload["semantic_layer_context"] == semantic_layer_context
    assert "prompt_context" not in user_payload


def test_openai_provider_schema_avoids_union_items_for_field_operations() -> None:
    response_schema = question_interpreter.QuestionFrameProposal.model_json_schema()
    field_operations_schema = response_schema["properties"]["field_operations"]

    assert "oneOf" not in json.dumps(field_operations_schema)


def test_openai_provider_schema_guides_supported_summary_intent() -> None:
    response_schema = question_interpreter.QuestionFrameProposal.model_json_schema()
    intent_schema = response_schema["properties"]["intent"]

    assert "Use summarize" in intent_schema["description"]
    assert "what was" in intent_schema["description"]
    assert "show" in intent_schema["description"]


def test_openai_provider_schema_rejects_empty_implicit_filters() -> None:
    response_schema = question_interpreter.QuestionFrameProposal.model_json_schema()
    field_operation_schema = response_schema["$defs"]["FieldOperationProposal"]
    field_operations_schema = response_schema["properties"]["field_operations"]
    operation_schema = field_operation_schema["properties"]["operation"]
    values_schema = field_operation_schema["properties"]["values"]

    assert "merely available in context" in field_operations_schema["description"]
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


def test_openai_provider_prompt_extracts_explicit_calendar_month_time_ranges() -> None:
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

    input_messages = typing.cast(
        list[dict[str, str]],
        parse_calls[0]["input"],
    )
    developer_prompt = input_messages[0]["content"]
    assert 'Use intent "summarize"' in developer_prompt
    assert '"what was ..."' in developer_prompt
    assert '"show ..."' in developer_prompt
    assert '"summarize ..."' in developer_prompt
    assert "complete calendar month and year" in developer_prompt
    assert "January 2026" in developer_prompt
    assert "2026-01-01" in developer_prompt
    assert "2026-01-31" in developer_prompt
    assert "Use only business-facing Semantic Layer labels supplied in" in (
        developer_prompt
    )
    assert "semantic_layer_context" in developer_prompt
    assert "may come from semantic_layer_context even when" in developer_prompt
    assert "When the selected metric_context has exactly one date" in (developer_prompt)
    assert "use that field for a complete calendar month and year" in (developer_prompt)
    assert "Never omit a complete calendar month" in developer_prompt
    assert 'return intent\n"summarize"' in developer_prompt
    assert 'operation "range_filter", field "order date"' in developer_prompt
    assert "not inventing a time range" in developer_prompt


def test_openai_provider_prompt_chooses_one_relevant_date_field() -> None:
    parse_calls: list[dict[str, object]] = []

    class FakeParsedResponse:
        output_parsed = test_support.question_frame_proposal()

    provider = _openai_provider_returning(
        FakeParsedResponse(),
        parse_calls=parse_calls,
    )

    provider.propose_question_frame(
        question="What was customer count by customer region in January 2026?",
        semantic_layer_context={"datasets": []},
    )

    input_messages = typing.cast(
        list[dict[str, str]],
        parse_calls[0]["input"],
    )
    developer_prompt = input_messages[0]["content"]
    assert "One explicit date phrase should produce at most one date" in (
        developer_prompt
    )
    assert "choose the one most" in developer_prompt
    assert "directly related to the requested metric" in developer_prompt
    assert "Do not add date" in developer_prompt
    assert "filters for unrelated fields" in developer_prompt
    assert "must not include operations for fields that are merely" in (
        developer_prompt
    )
    assert "use the metric_context" in developer_prompt
    assert "outside the selected metric's compatible fields" in developer_prompt
    assert "A field that" in developer_prompt
    assert "appears only under a different metric_context" in developer_prompt
    assert "Never return include_filter or exclude_filter with" in developer_prompt
    assert "values []" in developer_prompt
    assert "What was customer count by customer region in January 2026?" in (
        developer_prompt
    )
    assert 'operation "range_filter", field "created date"' in developer_prompt


def test_openai_provider_prompt_forbids_implicit_empty_filters() -> None:
    parse_calls: list[dict[str, object]] = []

    class FakeParsedResponse:
        output_parsed = test_support.question_frame_proposal()

    provider = _openai_provider_returning(
        FakeParsedResponse(),
        parse_calls=parse_calls,
    )

    provider.propose_question_frame(
        question="What was total revenue by region?",
        semantic_layer_context={"datasets": []},
    )

    input_messages = typing.cast(
        list[dict[str, str]],
        parse_calls[0]["input"],
    )
    developer_prompt = input_messages[0]["content"]
    assert "field_operations must be minimal and exhaustive" in developer_prompt
    assert "if a field operation is not" in developer_prompt
    assert "directly supported by words in the Data Question" in developer_prompt
    assert "Do not use include_filter or exclude_filter" in developer_prompt
    assert "included or excluded\nvalue" in developer_prompt
    assert "return no include_filter or exclude_filter" in developer_prompt
    assert "do not invent a\n  range_filter" in developer_prompt
    assert 'For "What was total revenue by region?"' in developer_prompt
    assert "exactly one field_operation" in developer_prompt
    assert 'operation "group_by", field "region"' in developer_prompt


def test_openai_provider_prompt_describes_dimension_value_filters() -> None:
    parse_calls: list[dict[str, object]] = []

    class FakeParsedResponse:
        output_parsed = test_support.question_frame_proposal()

    provider = _openai_provider_returning(
        FakeParsedResponse(),
        parse_calls=parse_calls,
    )

    provider.propose_question_frame(
        question="What was total revenue in the West region for all time?",
        semantic_layer_context={"datasets": []},
    )

    input_messages = typing.cast(
        list[dict[str, str]],
        parse_calls[0]["input"],
    )
    developer_prompt = input_messages[0]["content"]
    assert "Use include_filter when the user asks for one concrete value" in (
        developer_prompt
    )
    assert '"in the <value> <field label>"' in developer_prompt
    assert "Copy the\n  requested value into values" in developer_prompt
    assert (
        'For a dimension-value filter question like "What was total revenue'
        in developer_prompt
    )
    assert 'operation "include_filter", field "region"' in developer_prompt
    assert 'values ["West"]' in developer_prompt
    assert "Apply the same pattern to\nany single requested dimension value" in (
        developer_prompt
    )


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

    result = provider.propose_question_frame(
        question=test_support.CANONICAL_DATA_QUESTION,
        semantic_layer_context={"datasets": []},
    )

    assert result == question_interpreter.ProviderFailure(reason="cannot comply")


def test_openai_provider_maps_missing_parsed_output_to_provider_failure() -> None:
    class FakeMissingParsedResponse:
        output_parsed = None

    provider = _openai_provider_returning(FakeMissingParsedResponse())

    result = provider.propose_question_frame(
        question=test_support.CANONICAL_DATA_QUESTION,
        semantic_layer_context={"datasets": []},
    )

    assert result == question_interpreter.ProviderFailure(
        reason="OpenAI provider returned no parsed output"
    )

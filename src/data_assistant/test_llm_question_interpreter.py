import datetime
import typing

import pytest

import data_assistant.llm_question_interpreter as llm_question_interpreter
import data_assistant.semantic_layer.loader as semantic_layer_loader
import data_assistant.semantic_layer.testing_support as semantic_layer_testing
import data_assistant.workflow.contracts as contracts

_DEFAULT_TIME_RANGE = object()


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
        model="gpt-5.5",
    )
    assert override_config == (
        llm_question_interpreter.OpenAIQuestionInterpreterConfig(
            api_key="test-key",
            model="gpt-test-mini",
        )
    )


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
        question="What was total revenue by region in January 2026?",
        prompt_context={
            "metric_labels": ["total revenue"],
            "dimension_labels": ["region"],
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


def test_openai_provider_maps_refusal_to_provider_failure() -> None:
    class FakeRefusalResponse:
        output_parsed = None
        refusal = "cannot comply"

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
        question="What was total revenue by region in January 2026?",
        prompt_context={"datasets": []},
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
        question="What was total revenue by region in January 2026?",
        prompt_context={"datasets": []},
    )

    assert result == llm_question_interpreter.ProviderFailure(
        reason="OpenAI provider returned no parsed output"
    )


def test_provider_backed_interpreter_promotes_valid_question_frame_proposal() -> None:
    semantic_layer = semantic_layer_testing.semantic_layer_with_table()

    class FakeProvider:
        def propose_question_frame(
            self,
            *,
            question: str,
            prompt_context: object,
        ) -> llm_question_interpreter.QuestionFrameProposal:
            assert question == "What was total revenue by region in January 2026?"
            assert prompt_context is not None
            return _question_frame_proposal()

    result = llm_question_interpreter.interpret_question(
        question="What was total revenue by region in January 2026?",
        semantic_layer=semantic_layer,
        provider=FakeProvider(),
    )

    assert result == contracts.Success(
        contracts.QuestionFrame(
            intent="summarize",
            metric="total revenue",
            dimension="region",
            time_range=contracts.TimeRange(
                label="January 2026",
                start_date=datetime.date(2026, 1, 1),
                end_date=datetime.date(2026, 1, 31),
            ),
            filters=(),
            unresolved_ambiguities=(),
        )
    )


def test_provider_backed_interpreter_returns_typed_non_answer_for_missing_time_range(
) -> None:
    semantic_layer = semantic_layer_testing.semantic_layer_with_table()

    class FakeProvider:
        def propose_question_frame(
            self,
            *,
            question: str,
            prompt_context: object,
        ) -> llm_question_interpreter.QuestionFrameProposal:
            del question, prompt_context
            return _question_frame_proposal(time_range=None)

    result = llm_question_interpreter.interpret_question(
        question="What was total revenue by region?",
        semantic_layer=semantic_layer,
        provider=FakeProvider(),
    )

    assert result == contracts.NonAnswer(
        stage=contracts.NonAnswerStage.QUESTION_INTERPRETER,
        reason_code=contracts.NonAnswerReasonCode.MISSING_REQUIRED_FIELD,
        reason="The Data Question is missing required interpretation details.",
        unresolved_ambiguities=("time range",),
        next_step="Ask a clarification question before selecting data.",
    )


def test_provider_backed_interpreter_returns_typed_non_answer_for_unsupported_data(
) -> None:
    semantic_layer = semantic_layer_testing.semantic_layer_with_table()

    class FailIfCalledProvider:
        def propose_question_frame(
            self,
            *,
            question: str,
            prompt_context: object,
        ) -> llm_question_interpreter.ProviderFailure:
            del question, prompt_context
            raise AssertionError("provider should not be called")

    result = llm_question_interpreter.interpret_question(
        question=(
            "Can you use my CSV file to show total revenue by region in "
            "January 2026?"
        ),
        semantic_layer=semantic_layer,
        provider=FailIfCalledProvider(),
    )

    assert result == contracts.NonAnswer(
        stage=contracts.NonAnswerStage.QUESTION_INTERPRETER,
        reason_code=contracts.NonAnswerReasonCode.UNSUPPORTED_DATA,
        reason="User-provided CSV files are not supported data sources.",
        unresolved_ambiguities=("unsupported data",),
        next_step=(
            "Ask about an approved Curated Dataset in the Semantic Layer "
            "instead."
        ),
    )


def test_provider_backed_interpreter_returns_typed_non_answer_for_unsupported_intent(
) -> None:
    result = _interpret_with_provider_proposal(
        _question_frame_proposal(intent="forecast")
    )

    assert result == contracts.NonAnswer(
        stage=contracts.NonAnswerStage.QUESTION_INTERPRETER,
        reason_code=contracts.NonAnswerReasonCode.UNSUPPORTED_INTENT,
        reason=(
            "The Data Assistant does not support that Data Question intent "
            "yet."
        ),
        unresolved_ambiguities=("supported intent",),
        next_step="Ask: What was total revenue by region in January 2026?",
    )


def test_provider_backed_interpreter_returns_typed_non_answer_for_unknown_metric(
) -> None:
    result = _interpret_with_provider_proposal(
        _question_frame_proposal(metric="gross bookings")
    )

    assert result == contracts.NonAnswer(
        stage=contracts.NonAnswerStage.QUESTION_INTERPRETER,
        reason_code=contracts.NonAnswerReasonCode.UNKNOWN_SEMANTIC_LABEL,
        reason=(
            "The Data Assistant could not match the requested Semantic Layer "
            "labels."
        ),
        unresolved_ambiguities=("metric",),
        next_step="Use exact Semantic Layer metric and dimension labels.",
    )


def test_provider_backed_interpreter_returns_typed_non_answer_for_missing_dimension(
) -> None:
    result = _interpret_with_provider_proposal(
        _question_frame_proposal(dimension="")
    )

    assert result == contracts.NonAnswer(
        stage=contracts.NonAnswerStage.QUESTION_INTERPRETER,
        reason_code=contracts.NonAnswerReasonCode.MISSING_REQUIRED_FIELD,
        reason="The Data Question is missing required interpretation details.",
        unresolved_ambiguities=("dimension",),
        next_step="Ask a clarification question before selecting data.",
    )


def test_provider_backed_interpreter_returns_typed_non_answer_for_unsupported_filters(
) -> None:
    result = _interpret_with_provider_proposal(
        _question_frame_proposal(filters=("region = 'North'",))
    )

    assert result == contracts.NonAnswer(
        stage=contracts.NonAnswerStage.QUESTION_INTERPRETER,
        reason_code=contracts.NonAnswerReasonCode.UNSUPPORTED_FILTER,
        reason=(
            "The Data Assistant does not support provider-proposed filters "
            "yet."
        ),
        unresolved_ambiguities=("filters",),
        next_step="Ask the Data Question without filters for now.",
    )


def test_provider_backed_interpreter_returns_typed_non_answer_for_provider_failure(
) -> None:
    semantic_layer = semantic_layer_testing.semantic_layer_with_table()

    class FakeProvider:
        def propose_question_frame(
            self,
            *,
            question: str,
            prompt_context: object,
        ) -> llm_question_interpreter.ProviderFailure:
            del question, prompt_context
            return llm_question_interpreter.ProviderFailure(
                reason="provider unavailable",
            )

    result = llm_question_interpreter.interpret_question(
        question="What was total revenue by region in January 2026?",
        semantic_layer=semantic_layer,
        provider=FakeProvider(),
    )

    assert result == contracts.NonAnswer(
        stage=contracts.NonAnswerStage.QUESTION_INTERPRETER,
        reason_code=contracts.NonAnswerReasonCode.PROVIDER_FAILURE,
        reason=(
            "The Question Interpreter provider could not produce a proposal."
        ),
        unresolved_ambiguities=("provider failure",),
        next_step="Retry after the provider is available again.",
    )


def test_provider_backed_interpreter_rejects_invalid_provider_output() -> None:
    result = _interpret_with_bad_provider_result({"hello": "world"})

    assert result == contracts.NonAnswer(
        stage=contracts.NonAnswerStage.QUESTION_INTERPRETER,
        reason_code=contracts.NonAnswerReasonCode.INVALID_PROVIDER_OUTPUT,
        reason="The Question Interpreter provider returned invalid output.",
        unresolved_ambiguities=("provider output",),
        next_step="Fix the provider contract before retrying.",
    )


def test_provider_backed_interpreter_rejects_invalid_time_range_ordering() -> None:
    result = _interpret_with_provider_proposal(
        _question_frame_proposal(
            time_range=llm_question_interpreter.TimeRangeProposal(
                label="January 2026",
                start_date=datetime.date(2026, 1, 31),
                end_date=datetime.date(2026, 1, 1),
            )
        )
    )

    assert result == contracts.NonAnswer(
        stage=contracts.NonAnswerStage.QUESTION_INTERPRETER,
        reason_code=contracts.NonAnswerReasonCode.INVALID_PROVIDER_OUTPUT,
        reason="The Question Interpreter provider returned invalid output.",
        unresolved_ambiguities=("time range",),
        next_step="Fix the provider contract before retrying.",
    )

def test_build_prompt_context_uses_only_business_facing_semantic_layer_fields() -> None:
    semantic_layer = semantic_layer_loader.load_semantic_layer()

    prompt_context = llm_question_interpreter.build_prompt_context(semantic_layer)

    assert prompt_context == {
        "datasets": [
            {
                "name": "Commerce Revenue",
                "information_types": [
                    "revenue",
                    "regional performance",
                    "order activity",
                    "customer metadata",
                ],
                "example_questions": [
                    "What was total revenue by region in January 2026?",
                ],
                "metric_labels": ["customer count", "total revenue"],
                "dimension_labels": ["customer region", "region"],
            },
        ],
        "metric_labels": ["customer count", "total revenue"],
        "dimension_labels": ["customer region", "region"],
        "supported_intents": ["summarize"],
    }
    rendered_prompt_context = repr(prompt_context)
    assert "commerce" not in rendered_prompt_context
    assert "orders" not in rendered_prompt_context
    assert "customers" not in rendered_prompt_context
    assert "total_revenue" not in rendered_prompt_context
    assert "customer_region" not in rendered_prompt_context
    assert "sum(revenue)" not in rendered_prompt_context
    assert "allowed_identity_ids" not in rendered_prompt_context
    assert (
        "Commerce order data refreshed through 2026-01-31."
        not in rendered_prompt_context
    )


def test_golden_question_evals_cover_expected_contracts() -> None:
    eval_cases = (
        GoldenEvalCase(
            name="happy_path",
            provider_proposal=_question_frame_proposal(),
            expected=contracts.Success(
                contracts.QuestionFrame(
                    intent="summarize",
                    metric="total revenue",
                    dimension="region",
                    time_range=contracts.TimeRange(
                        label="January 2026",
                        start_date=datetime.date(2026, 1, 1),
                        end_date=datetime.date(2026, 1, 31),
                    ),
                    filters=(),
                    unresolved_ambiguities=(),
                )
            ),
        ),
        GoldenEvalCase(
            name="missing_time_range",
            provider_proposal=_question_frame_proposal(time_range=None),
            expected=contracts.NonAnswer(
                stage=contracts.NonAnswerStage.QUESTION_INTERPRETER,
                reason_code=contracts.NonAnswerReasonCode.MISSING_REQUIRED_FIELD,
                reason="The Data Question is missing required interpretation details.",
                unresolved_ambiguities=("time range",),
                next_step="Ask a clarification question before selecting data.",
            ),
        ),
        GoldenEvalCase(
            name="unsupported_data",
            question=(
                "Can you use my CSV file to show total revenue by region in "
                "January 2026?"
            ),
            provider_proposal=None,
            expected=contracts.NonAnswer(
                stage=contracts.NonAnswerStage.QUESTION_INTERPRETER,
                reason_code=contracts.NonAnswerReasonCode.UNSUPPORTED_DATA,
                reason="User-provided CSV files are not supported data sources.",
                unresolved_ambiguities=("unsupported data",),
                next_step=(
                    "Ask about an approved Curated Dataset in the Semantic "
                    "Layer instead."
                ),
            ),
        ),
        GoldenEvalCase(
            name="unsupported_intent",
            provider_proposal=_question_frame_proposal(intent="forecast"),
            expected=contracts.NonAnswer(
                stage=contracts.NonAnswerStage.QUESTION_INTERPRETER,
                reason_code=contracts.NonAnswerReasonCode.UNSUPPORTED_INTENT,
                reason=(
                    "The Data Assistant does not support that Data Question "
                    "intent yet."
                ),
                unresolved_ambiguities=("supported intent",),
                next_step="Ask: What was total revenue by region in January 2026?",
            ),
        ),
        GoldenEvalCase(
            name="hallucinated_metric",
            provider_proposal=_question_frame_proposal(metric="gross bookings"),
            expected=contracts.NonAnswer(
                stage=contracts.NonAnswerStage.QUESTION_INTERPRETER,
                reason_code=contracts.NonAnswerReasonCode.UNKNOWN_SEMANTIC_LABEL,
                reason=(
                    "The Data Assistant could not match the requested "
                    "Semantic Layer labels."
                ),
                unresolved_ambiguities=("metric",),
                next_step="Use exact Semantic Layer metric and dimension labels.",
            ),
        ),
        GoldenEvalCase(
            name="missing_dimension",
            provider_proposal=_question_frame_proposal(dimension=""),
            expected=contracts.NonAnswer(
                stage=contracts.NonAnswerStage.QUESTION_INTERPRETER,
                reason_code=contracts.NonAnswerReasonCode.MISSING_REQUIRED_FIELD,
                reason="The Data Question is missing required interpretation details.",
                unresolved_ambiguities=("dimension",),
                next_step="Ask a clarification question before selecting data.",
            ),
        ),
        GoldenEvalCase(
            name="unsupported_filters",
            provider_proposal=_question_frame_proposal(filters=("region = 'North'",)),
            expected=contracts.NonAnswer(
                stage=contracts.NonAnswerStage.QUESTION_INTERPRETER,
                reason_code=contracts.NonAnswerReasonCode.UNSUPPORTED_FILTER,
                reason=(
                    "The Data Assistant does not support provider-proposed "
                    "filters yet."
                ),
                unresolved_ambiguities=("filters",),
                next_step="Ask the Data Question without filters for now.",
            ),
        ),
        GoldenEvalCase(
            name="invalid_time_range_ordering",
            provider_proposal=_question_frame_proposal(
                time_range=llm_question_interpreter.TimeRangeProposal(
                    label="January 2026",
                    start_date=datetime.date(2026, 1, 31),
                    end_date=datetime.date(2026, 1, 1),
                )
            ),
            expected=contracts.NonAnswer(
                stage=contracts.NonAnswerStage.QUESTION_INTERPRETER,
                reason_code=contracts.NonAnswerReasonCode.INVALID_PROVIDER_OUTPUT,
                reason="The Question Interpreter provider returned invalid output.",
                unresolved_ambiguities=("time range",),
                next_step="Fix the provider contract before retrying.",
            ),
        ),
    )

    for case in eval_cases:
        provider = _proposal_provider(case.provider_proposal)
        result = llm_question_interpreter.interpret_question(
            question=case.question,
            semantic_layer=semantic_layer_testing.semantic_layer_with_table(),
            provider=provider,
        )
        assert_matches_expected_result(case.expected, result)


class GoldenEvalCase(typing.NamedTuple):
    name: str
    provider_proposal: llm_question_interpreter.QuestionFrameProposal | None
    expected: contracts.StageResult[contracts.QuestionFrame]
    question: str = "What was total revenue by region in January 2026?"


def assert_matches_expected_result(
    expected: contracts.StageResult[contracts.QuestionFrame],
    actual: contracts.StageResult[contracts.QuestionFrame],
) -> None:
    assert actual == expected


def _interpret_with_provider_proposal(
    provider_proposal: llm_question_interpreter.QuestionFrameProposal,
) -> contracts.StageResult[contracts.QuestionFrame]:
    return llm_question_interpreter.interpret_question(
        question="What was total revenue by region in January 2026?",
        semantic_layer=semantic_layer_testing.semantic_layer_with_table(),
        provider=_proposal_provider(provider_proposal),
    )


def _interpret_with_bad_provider_result(
    provider_result: object,
) -> contracts.StageResult[contracts.QuestionFrame]:
    return llm_question_interpreter.interpret_question(
        question="What was total revenue by region in January 2026?",
        semantic_layer=semantic_layer_testing.semantic_layer_with_table(),
        provider=_bad_provider(provider_result),
    )


def _proposal_provider(
    provider_proposal: llm_question_interpreter.QuestionFrameProposal | None,
) -> llm_question_interpreter.QuestionInterpreterProvider:
    class FakeProvider:
        def propose_question_frame(
            self,
            *,
            question: str,
            prompt_context: dict[str, object],
        ) -> llm_question_interpreter.QuestionFrameProposal:
            del question, prompt_context
            if provider_proposal is None:
                raise AssertionError("provider should not be called")
            return provider_proposal

    return FakeProvider()


def _bad_provider(
    provider_result: object,
) -> llm_question_interpreter.QuestionInterpreterProvider:
    class BadProvider:
        def propose_question_frame(
            self,
            *,
            question: str,
            prompt_context: dict[str, object],
        ) -> llm_question_interpreter.QuestionFrameProposal:
            del question, prompt_context
            return typing.cast(
                llm_question_interpreter.QuestionFrameProposal,
                provider_result,
            )

    return BadProvider()


def _question_frame_proposal(
    *,
    intent: str | None = "summarize",
    metric: str | None = "total revenue",
    dimension: str | None = "region",
    time_range: llm_question_interpreter.TimeRangeProposal | None | object = (
        _DEFAULT_TIME_RANGE
    ),
    filters: tuple[str, ...] = (),
) -> llm_question_interpreter.QuestionFrameProposal:
    if time_range is _DEFAULT_TIME_RANGE:
        active_time_range: llm_question_interpreter.TimeRangeProposal | None = (
            llm_question_interpreter.TimeRangeProposal(
                label="January 2026",
                start_date=datetime.date(2026, 1, 1),
                end_date=datetime.date(2026, 1, 31),
            )
        )
    else:
        active_time_range = typing.cast(
            llm_question_interpreter.TimeRangeProposal | None,
            time_range,
        )

    return llm_question_interpreter.QuestionFrameProposal(
        intent=intent,
        metric=metric,
        dimension=dimension,
        time_range=active_time_range,
        filters=filters,
    )

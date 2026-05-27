import datetime
import typing

import data_assistant.llm_question_interpreter as llm_question_interpreter
import data_assistant.semantic_layer.loader as semantic_layer_loader
import data_assistant.semantic_layer.testing_support as semantic_layer_testing
import data_assistant.workflow.contracts as contracts


def test_provider_backed_interpreter_promotes_valid_question_frame_proposal() -> None:
    semantic_layer = semantic_layer_testing.semantic_layer_with_table()

    class FakeProvider:
        def propose_question_frame(
            self,
            *,
            question: str,
            prompt_context: object,
        ) -> object:
            assert question == "What was total revenue by region in January 2026?"
            assert prompt_context is not None
            return llm_question_interpreter.QuestionFrameProposal(
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
        ) -> object:
            del question, prompt_context
            return llm_question_interpreter.QuestionFrameProposal(
                intent="summarize",
                metric="total revenue",
                dimension="region",
                time_range=None,
                filters=(),
            )

    result = llm_question_interpreter.interpret_question(
        question="What was total revenue by region?",
        semantic_layer=semantic_layer,
        provider=FakeProvider(),
    )

    assert result == contracts.NonAnswer(
        stage="question_interpreter",
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
        ) -> object:
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
        stage="question_interpreter",
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
    result = _interpret_with_provider_payload(
        {
            "intent": "forecast",
            "metric": "total revenue",
            "dimension": "region",
            "time_range": _january_2026_time_range_payload(),
            "filters": (),
        }
    )

    assert result == contracts.NonAnswer(
        stage="question_interpreter",
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
    result = _interpret_with_provider_payload(
        {
            "intent": "summarize",
            "metric": "gross bookings",
            "dimension": "region",
            "time_range": _january_2026_time_range_payload(),
            "filters": (),
        }
    )

    assert result == contracts.NonAnswer(
        stage="question_interpreter",
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
    result = _interpret_with_provider_payload(
        {
            "intent": "summarize",
            "metric": "total revenue",
            "dimension": "",
            "time_range": _january_2026_time_range_payload(),
            "filters": (),
        }
    )

    assert result == contracts.NonAnswer(
        stage="question_interpreter",
        reason_code=contracts.NonAnswerReasonCode.MISSING_REQUIRED_FIELD,
        reason="The Data Question is missing required interpretation details.",
        unresolved_ambiguities=("dimension",),
        next_step="Ask a clarification question before selecting data.",
    )


def test_provider_backed_interpreter_returns_typed_non_answer_for_unsupported_filters(
) -> None:
    result = _interpret_with_provider_payload(
        {
            "intent": "summarize",
            "metric": "total revenue",
            "dimension": "region",
            "time_range": _january_2026_time_range_payload(),
            "filters": ("region = 'North'",),
        }
    )

    assert result == contracts.NonAnswer(
        stage="question_interpreter",
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
        ) -> object:
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
        stage="question_interpreter",
        reason_code=contracts.NonAnswerReasonCode.PROVIDER_FAILURE,
        reason=(
            "The Question Interpreter provider could not produce a proposal."
        ),
        unresolved_ambiguities=("provider failure",),
        next_step="Retry after the provider is available again.",
    )


def test_provider_backed_interpreter_rejects_invalid_provider_output() -> None:
    result = _interpret_with_provider_payload({"hello": "world"})

    assert result == contracts.NonAnswer(
        stage="question_interpreter",
        reason_code=contracts.NonAnswerReasonCode.INVALID_PROVIDER_OUTPUT,
        reason="The Question Interpreter provider returned invalid output.",
        unresolved_ambiguities=("provider output",),
        next_step="Fix the provider contract before retrying.",
    )


def test_provider_backed_interpreter_rejects_invalid_time_range_ordering() -> None:
    result = _interpret_with_provider_payload(
        {
            "intent": "summarize",
            "metric": "total revenue",
            "dimension": "region",
            "time_range": {
                "label": "January 2026",
                "start_date": "2026-01-31",
                "end_date": "2026-01-01",
            },
            "filters": (),
        }
    )

    assert result == contracts.NonAnswer(
        stage="question_interpreter",
        reason_code=contracts.NonAnswerReasonCode.INVALID_PROVIDER_OUTPUT,
        reason="The Question Interpreter provider returned invalid output.",
        unresolved_ambiguities=("time range",),
        next_step="Fix the provider contract before retrying.",
    )


def test_provider_backed_interpreter_rejects_authority_drift_fields() -> None:
    result = _interpret_with_provider_payload(
        {
            "intent": "summarize",
            "metric": "total revenue",
            "dimension": "region",
            "time_range": _january_2026_time_range_payload(),
            "filters": (),
            "dataset_id": "commerce",
        }
    )

    assert result == contracts.NonAnswer(
        stage="question_interpreter",
        reason_code=contracts.NonAnswerReasonCode.UNSAFE_AUTHORITY_DRIFT,
        reason=(
            "The Question Interpreter provider proposed retrieval authority "
            "it does not own."
        ),
        unresolved_ambiguities=("authority drift",),
        next_step=(
            "Remove dataset, table, SQL, and raw schema authority from the "
            "provider output."
        ),
    )


def test_build_prompt_context_uses_only_business_facing_semantic_layer_fields() -> None:
    semantic_layer = semantic_layer_loader.load_semantic_layer()

    prompt_context = llm_question_interpreter.build_prompt_context(semantic_layer)

    assert prompt_context.datasets == (
        llm_question_interpreter.PromptContextDataset(
            dataset_id="commerce",
            name="Commerce Revenue",
            information_types=(
                "revenue",
                "regional performance",
                "order activity",
                "customer metadata",
            ),
            example_questions=(
                "What was total revenue by region in January 2026?",
            ),
            metric_labels=("customer count", "total revenue"),
            dimension_labels=("customer region", "region"),
        ),
    )
    rendered_prompt_context = repr(prompt_context)
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
            provider_payload={
                "intent": "summarize",
                "metric": "total revenue",
                "dimension": "region",
                "time_range": _january_2026_time_range_payload(),
                "filters": (),
            },
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
            provider_payload={
                "intent": "summarize",
                "metric": "total revenue",
                "dimension": "region",
                "time_range": None,
                "filters": (),
            },
            expected=contracts.NonAnswer(
                stage="question_interpreter",
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
            provider_payload=None,
            expected=contracts.NonAnswer(
                stage="question_interpreter",
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
            provider_payload={
                "intent": "forecast",
                "metric": "total revenue",
                "dimension": "region",
                "time_range": _january_2026_time_range_payload(),
                "filters": (),
            },
            expected=contracts.NonAnswer(
                stage="question_interpreter",
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
            provider_payload={
                "intent": "summarize",
                "metric": "gross bookings",
                "dimension": "region",
                "time_range": _january_2026_time_range_payload(),
                "filters": (),
            },
            expected=contracts.NonAnswer(
                stage="question_interpreter",
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
            provider_payload={
                "intent": "summarize",
                "metric": "total revenue",
                "dimension": "",
                "time_range": _january_2026_time_range_payload(),
                "filters": (),
            },
            expected=contracts.NonAnswer(
                stage="question_interpreter",
                reason_code=contracts.NonAnswerReasonCode.MISSING_REQUIRED_FIELD,
                reason="The Data Question is missing required interpretation details.",
                unresolved_ambiguities=("dimension",),
                next_step="Ask a clarification question before selecting data.",
            ),
        ),
        GoldenEvalCase(
            name="unsupported_filters",
            provider_payload={
                "intent": "summarize",
                "metric": "total revenue",
                "dimension": "region",
                "time_range": _january_2026_time_range_payload(),
                "filters": ("region = 'North'",),
            },
            expected=contracts.NonAnswer(
                stage="question_interpreter",
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
            provider_payload={
                "intent": "summarize",
                "metric": "total revenue",
                "dimension": "region",
                "time_range": {
                    "label": "January 2026",
                    "start_date": "2026-01-31",
                    "end_date": "2026-01-01",
                },
                "filters": (),
            },
            expected=contracts.NonAnswer(
                stage="question_interpreter",
                reason_code=contracts.NonAnswerReasonCode.INVALID_PROVIDER_OUTPUT,
                reason="The Question Interpreter provider returned invalid output.",
                unresolved_ambiguities=("time range",),
                next_step="Fix the provider contract before retrying.",
            ),
        ),
    )

    for case in eval_cases:
        provider = _payload_provider(case.provider_payload)
        result = llm_question_interpreter.interpret_question(
            question=case.question,
            semantic_layer=semantic_layer_testing.semantic_layer_with_table(),
            provider=provider,
        )
        assert_matches_expected_result(case.expected, result)


class GoldenEvalCase(typing.NamedTuple):
    name: str
    provider_payload: object
    expected: contracts.StageResult[contracts.QuestionFrame]
    question: str = "What was total revenue by region in January 2026?"


def assert_matches_expected_result(
    expected: contracts.StageResult[contracts.QuestionFrame],
    actual: contracts.StageResult[contracts.QuestionFrame],
) -> None:
    assert actual == expected


def _interpret_with_provider_payload(
    provider_payload: object,
) -> contracts.StageResult[contracts.QuestionFrame]:
    return llm_question_interpreter.interpret_question(
        question="What was total revenue by region in January 2026?",
        semantic_layer=semantic_layer_testing.semantic_layer_with_table(),
        provider=_payload_provider(provider_payload),
    )


def _payload_provider(
    provider_payload: object,
) -> llm_question_interpreter.QuestionInterpreterProvider:
    class FakeProvider:
        def propose_question_frame(
            self,
            *,
            question: str,
            prompt_context: llm_question_interpreter.PromptContext,
        ) -> object:
            del question, prompt_context
            return provider_payload

    return FakeProvider()


def _january_2026_time_range_payload() -> dict[str, str]:
    return {
        "label": "January 2026",
        "start_date": "2026-01-01",
        "end_date": "2026-01-31",
    }

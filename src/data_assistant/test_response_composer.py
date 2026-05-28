import data_assistant.llm_question_interpreter as llm_question_interpreter
import data_assistant.response_composer as response_composer
import data_assistant.testing_support as testing_support
import data_assistant.workflow.contracts as contracts
import data_assistant.workflow.runner as workflow_runner


def test_response_composer_returns_plain_text_with_trust_summary(
    canonical_question: str,
    connect_orders: testing_support.OrdersConnector,
    canonical_question_provider: llm_question_interpreter.QuestionInterpreterProvider,
    allowed_internal_identity: contracts.InternalIdentity,
) -> None:
    order_rows = (
        ("2026-01-03", "North", "1200.00"),
        ("2026-01-08", "South", "850.00"),
        ("2026-01-15", "West", "1600.00"),
        ("2026-01-20", " ", "250.00"),
        ("2026-01-22", "North", "300.00"),
        ("2026-01-28", "East", "950.00"),
        ("2026-01-29", "East", None),
        ("2026-02-01", None, None),
    )
    with connect_orders(order_rows) as connection:
        run = workflow_runner.run_data_assistant(
            connection,
            canonical_question,
            question_interpreter_provider=canonical_question_provider,
            internal_identity=allowed_internal_identity,
        )

    assert isinstance(run, contracts.DataAssistantRun)
    assert run.final_response.response_kind == "answer"
    assert (
        "Total revenue in January 2026 was $5,150.00, grouped across 5 regions."
        in run.final_response.text
    )
    assert "- Unknown: $250.00" in run.final_response.text
    assert "Trust Summary:" in run.final_response.text
    assert run.final_response.trust_summary == contracts.TrustSummary(
        datasets=("Commerce Revenue",),
        dataset_tables=("orders",),
        time_range="January 2026",
        filters=(),
        freshness="Commerce order data refreshed through 2026-01-31.",
        caveats=(
            "1 row excluded because revenue was missing.",
            "1 row grouped under Unknown because region was missing.",
        ),
        limitations=(),
    )
    assert "customers" not in run.final_response.text


def test_response_composer_returns_final_response_for_non_answer() -> None:
    response = response_composer.compose_non_answer_response(
        contracts.NonAnswer(
            stage=contracts.NonAnswerStage.QUESTION_INTERPRETER,
            reason_code=contracts.NonAnswerReasonCode.UNSUPPORTED_DATA,
            reason="User-provided CSV files are not supported data sources.",
            unresolved_ambiguities=("unsupported data",),
            next_step=(
                "Ask about an approved Curated Dataset in the Semantic Layer "
                "instead."
            ),
        )
    )

    assert response == contracts.FinalResponse(
        text=(
            "I cannot answer safely because user-provided CSV files are not "
            "supported data sources.\n\n"
            "Next step: Ask about an approved Curated Dataset in the "
            "Semantic Layer instead.\n\n"
            "Trust Summary: Limitations: User-provided CSV files are not "
            "supported data sources."
        ),
        trust_summary=contracts.TrustSummary(
            limitations=("User-provided CSV files are not supported data sources.",),
        ),
        response_kind="unsupported",
    )


def test_response_composer_returns_safe_access_denial_contract() -> None:
    response = response_composer.compose_non_answer_response(
        contracts.NonAnswer(
            stage=contracts.NonAnswerStage.ACCESS_CONTROLLER,
            reason_code=contracts.NonAnswerReasonCode.ACCESS_DENIED,
            reason="You do not have access to the commerce Curated Dataset.",
            unresolved_ambiguities=(),
            next_step=(
                "Ask a data owner to grant Dataset Access or ask about "
                "available data."
            ),
            datasets=("commerce",),
        )
    )

    assert response.response_kind == "access_denial"
    assert response.trust_summary == contracts.TrustSummary(
        datasets=("commerce",),
        limitations=("You do not have access to the commerce Curated Dataset.",),
    )
    assert "Curated Dataset: commerce." in response.text
    assert "Dataset Table:" not in response.text
    assert "Filters:" not in response.text
    assert "Freshness:" not in response.text


def test_response_composer_marks_clarification_needed_non_answer() -> None:
    response = response_composer.compose_non_answer_response(
        contracts.NonAnswer(
            stage=contracts.NonAnswerStage.QUESTION_INTERPRETER,
            reason_code=contracts.NonAnswerReasonCode.MISSING_REQUIRED_FIELD,
            reason="The Data Question is missing required interpretation details.",
            unresolved_ambiguities=("time range",),
            next_step="Ask a clarification question before selecting data.",
        )
    )

    assert response.response_kind == "clarification_needed"
    assert response.trust_summary == contracts.TrustSummary(
        limitations=(
            "The Data Question is missing required interpretation details.",
        ),
    )

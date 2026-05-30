import pandas as pd
import pytest

import data_assistant.response_composer as response_composer
import data_assistant.workflow.contracts as contracts


def _non_answer(
    *,
    stage: contracts.NonAnswerStage = contracts.NonAnswerStage.QUESTION_INTERPRETER,
    reason_code: contracts.NonAnswerReasonCode = (
        contracts.NonAnswerReasonCode.UNSUPPORTED_DATA
    ),
    reason: str = "User-provided CSV files are not supported data sources.",
    unresolved_ambiguities: tuple[str, ...] = ("unsupported data",),
    next_step: str = (
        "Ask about an approved Curated Dataset in the Semantic Layer instead."
    ),
    datasets: tuple[str, ...] = (),
) -> contracts.NonAnswer:
    return contracts.NonAnswer(
        stage=stage,
        reason_code=reason_code,
        reason=reason,
        unresolved_ambiguities=unresolved_ambiguities,
        next_step=next_step,
        datasets=datasets,
    )


def test_response_composer_returns_plain_text_with_trust_summary() -> None:
    response = response_composer.compose_final_response(
        contracts.AnswerDraft(
            summary=(
                "Total revenue in January 2026 was $2,050.00, grouped across "
                "2 regions."
            ),
            key_data=pd.DataFrame(
                {
                    "dimension_value": ("North", "South"),
                    "metric_value": (1200.0, 850.0),
                }
            ),
            datasets_used=("Commerce Revenue",),
            dataset_tables_used=("orders",),
            time_range="January 2026",
            filters=(),
            freshness="Commerce order data refreshed through 2026-01-31.",
            caveats=("1 row excluded because revenue was missing.",),
        )
    )

    assert response.response_kind == contracts.ResponseKind.ANSWER
    assert (
        "Total revenue in January 2026 was $2,050.00, grouped across 2 regions."
        in response.text
    )
    assert "- North: $1,200.00" in response.text
    assert "- South: $850.00" in response.text
    assert "Trust Summary:" in response.text
    assert response.trust_summary == contracts.TrustSummary(
        datasets=("Commerce Revenue",),
        dataset_tables=("orders",),
        time_range="January 2026",
        filters=(),
        freshness="Commerce order data refreshed through 2026-01-31.",
        caveats=("1 row excluded because revenue was missing.",),
        limitations=(),
    )


def test_response_composer_returns_final_response_for_non_answer() -> None:
    response = response_composer.compose_non_answer_response(_non_answer())

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
        response_kind=contracts.ResponseKind.UNSUPPORTED,
    )


def test_response_composer_marks_missing_required_field_as_clarification() -> None:
    response = response_composer.compose_non_answer_response(
        _non_answer(
            reason_code=contracts.NonAnswerReasonCode.MISSING_REQUIRED_FIELD,
            reason="The Data Question needs a metric before data selection.",
            unresolved_ambiguities=("metric",),
            next_step="Ask which business metric the team member wants.",
        )
    )

    assert response.response_kind == contracts.ResponseKind.CLARIFICATION_NEEDED
    assert response.text.startswith("I cannot answer safely yet because")
    assert "The Data Question needs a metric before data selection." in (
        response.trust_summary.limitations
    )
    assert "Ask which business metric the team member wants." in response.text


@pytest.mark.parametrize(
    ("stage", "reason_code", "reason", "unresolved_ambiguities", "next_step"),
    [
        pytest.param(
            contracts.NonAnswerStage.SEMANTIC_ROUTER,
            contracts.NonAnswerReasonCode.AMBIGUOUS_DATASET,
            "Multiple Curated Datasets could answer this Data Question.",
            ("dataset choice",),
            "Ask which Curated Dataset the team member wants.",
            id="ambiguous dataset",
        ),
        pytest.param(
            contracts.NonAnswerStage.DATA_REQUESTER,
            contracts.NonAnswerReasonCode.AMBIGUOUS_TABLE,
            "Multiple Dataset Tables can satisfy this Data Question.",
            ("table choice",),
            "Ask which Dataset Table should be used.",
            id="ambiguous table",
        ),
    ],
)
def test_response_composer_marks_ambiguity_as_clarification(
    stage: contracts.NonAnswerStage,
    reason_code: contracts.NonAnswerReasonCode,
    reason: str,
    unresolved_ambiguities: tuple[str, ...],
    next_step: str,
) -> None:
    response = response_composer.compose_non_answer_response(
        _non_answer(
            stage=stage,
            reason_code=reason_code,
            reason=reason,
            unresolved_ambiguities=unresolved_ambiguities,
            next_step=next_step,
        )
    )

    assert response.response_kind == contracts.ResponseKind.CLARIFICATION_NEEDED
    assert response.text.startswith("I cannot answer safely yet because")
    assert next_step in response.text


@pytest.mark.parametrize(
    ("reason_code", "reason", "next_step"),
    [
        pytest.param(
            contracts.NonAnswerReasonCode.UNSUPPORTED_DATA,
            "User-provided CSV files are not supported data sources.",
            "Ask about an approved Curated Dataset in the Semantic Layer instead.",
            id="unsupported data",
        ),
        pytest.param(
            contracts.NonAnswerReasonCode.NO_MATCHING_DATASET,
            "No Curated Dataset can answer this Data Question.",
            "Ask about available Curated Datasets instead.",
            id="no matching dataset",
        ),
        pytest.param(
            contracts.NonAnswerReasonCode.PROVIDER_FAILURE,
            "The Question Interpreter provider failed before returning output.",
            "Try again or use the deterministic demo path.",
            id="provider failure",
        ),
    ],
)
def test_response_composer_marks_unsupported_non_answers_without_yet_wording(
    reason_code: contracts.NonAnswerReasonCode,
    reason: str,
    next_step: str,
) -> None:
    response = response_composer.compose_non_answer_response(
        _non_answer(
            reason_code=reason_code,
            reason=reason,
            unresolved_ambiguities=(),
            next_step=next_step,
        )
    )

    assert response.response_kind == contracts.ResponseKind.UNSUPPORTED
    assert response.text.startswith("I cannot answer safely because")
    assert "safely yet" not in response.text
    assert next_step in response.text


def test_response_composer_omits_sensitive_details_from_access_denial() -> None:
    response = response_composer.compose_non_answer_response(
        _non_answer(
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

    assert "Curated Dataset: commerce." in response.text
    assert "Dataset Table:" not in response.text
    assert "Filters:" not in response.text
    assert "Freshness:" not in response.text

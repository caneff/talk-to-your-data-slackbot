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

    assert response.response_kind == "answer"
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
        response_kind="unsupported",
    )


@pytest.mark.parametrize(
    ("non_answer", "expected_response_kind", "expected_trust_summary"),
    [
        pytest.param(
            _non_answer(),
            "unsupported",
            contracts.TrustSummary(
                limitations=(
                    "User-provided CSV files are not supported data sources.",
                ),
            ),
            id="unsupported",
        ),
        pytest.param(
            _non_answer(
                stage=contracts.NonAnswerStage.ACCESS_CONTROLLER,
                reason_code=contracts.NonAnswerReasonCode.ACCESS_DENIED,
                reason="You do not have access to the commerce Curated Dataset.",
                unresolved_ambiguities=(),
                next_step="Ask a data owner to grant Dataset Access.",
                datasets=("commerce",),
            ),
            "access_denial",
            contracts.TrustSummary(
                datasets=("commerce",),
                limitations=(
                    "You do not have access to the commerce Curated Dataset.",
                ),
            ),
            id="access denial",
        ),
        pytest.param(
            _non_answer(
                reason_code=contracts.NonAnswerReasonCode.MISSING_REQUIRED_FIELD,
                reason=(
                    "The Data Question is missing required interpretation details."
                ),
                unresolved_ambiguities=("time range",),
                next_step="Ask a clarification question before selecting data.",
            ),
            "clarification_needed",
            contracts.TrustSummary(
                limitations=(
                    "The Data Question is missing required interpretation details.",
                ),
            ),
            id="clarification needed",
        ),
    ],
)
def test_response_composer_maps_non_answer_kind_and_trust_summary(
    non_answer: contracts.NonAnswer,
    expected_response_kind: str,
    expected_trust_summary: contracts.TrustSummary,
) -> None:
    response = response_composer.compose_non_answer_response(non_answer)

    assert response.response_kind == expected_response_kind
    assert response.trust_summary == expected_trust_summary
    assert non_answer.next_step in response.text


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

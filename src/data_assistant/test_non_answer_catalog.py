import data_assistant.non_answer_catalog as non_answer_catalog
import data_assistant.workflow.contracts as contracts


def test_response_kind_for_classifies_non_answer_reason_categories() -> None:
    access_denial_reasons = {contracts.NonAnswerReasonCode.ACCESS_DENIED}
    clarification_reasons = {
        contracts.NonAnswerReasonCode.MISSING_REQUIRED_FIELD,
        contracts.NonAnswerReasonCode.AMBIGUOUS_DATASET,
        contracts.NonAnswerReasonCode.AMBIGUOUS_TABLE,
    }
    unsupported_reasons = set(contracts.NonAnswerReasonCode) - (
        access_denial_reasons | clarification_reasons
    )

    assert {
        reason_code
        for reason_code in contracts.NonAnswerReasonCode
        if non_answer_catalog.response_kind_for(reason_code)
        == contracts.ResponseKind.ACCESS_DENIAL
    } == access_denial_reasons
    assert {
        reason_code
        for reason_code in contracts.NonAnswerReasonCode
        if non_answer_catalog.response_kind_for(reason_code)
        == contracts.ResponseKind.CLARIFICATION_NEEDED
    } == clarification_reasons
    assert {
        reason_code
        for reason_code in contracts.NonAnswerReasonCode
        if non_answer_catalog.response_kind_for(reason_code)
        == contracts.ResponseKind.UNSUPPORTED
    } == unsupported_reasons


def test_response_kind_categories_cover_every_non_answer_reason() -> None:
    classified_reasons = {
        reason_code
        for reason_code in contracts.NonAnswerReasonCode
        if non_answer_catalog.response_kind_for(reason_code)
        != contracts.ResponseKind.ANSWER
    }

    assert classified_reasons == set(contracts.NonAnswerReasonCode)

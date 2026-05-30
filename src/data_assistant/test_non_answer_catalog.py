import pytest

import data_assistant.non_answer_catalog as non_answer_catalog
import data_assistant.workflow.contracts as contracts


@pytest.mark.parametrize(
    ("reason_code", "expected_response_kind"),
    [
        pytest.param(
            contracts.NonAnswerReasonCode.ACCESS_DENIED,
            contracts.ResponseKind.ACCESS_DENIAL,
            id="access denied",
        ),
        pytest.param(
            contracts.NonAnswerReasonCode.MISSING_REQUIRED_FIELD,
            contracts.ResponseKind.CLARIFICATION_NEEDED,
            id="missing required field",
        ),
        pytest.param(
            contracts.NonAnswerReasonCode.AMBIGUOUS_DATASET,
            contracts.ResponseKind.CLARIFICATION_NEEDED,
            id="ambiguous dataset",
        ),
        pytest.param(
            contracts.NonAnswerReasonCode.AMBIGUOUS_TABLE,
            contracts.ResponseKind.CLARIFICATION_NEEDED,
            id="ambiguous table",
        ),
        pytest.param(
            contracts.NonAnswerReasonCode.INVALID_PROVIDER_OUTPUT,
            contracts.ResponseKind.UNSUPPORTED,
            id="invalid provider output",
        ),
        pytest.param(
            contracts.NonAnswerReasonCode.NO_MATCHING_DATASET,
            contracts.ResponseKind.UNSUPPORTED,
            id="no matching dataset",
        ),
        pytest.param(
            contracts.NonAnswerReasonCode.NO_MATCHING_TABLE,
            contracts.ResponseKind.UNSUPPORTED,
            id="no matching table",
        ),
        pytest.param(
            contracts.NonAnswerReasonCode.PROVIDER_FAILURE,
            contracts.ResponseKind.UNSUPPORTED,
            id="provider failure",
        ),
        pytest.param(
            contracts.NonAnswerReasonCode.UNKNOWN_SEMANTIC_LABEL,
            contracts.ResponseKind.UNSUPPORTED,
            id="unknown semantic label",
        ),
        pytest.param(
            contracts.NonAnswerReasonCode.UNSUPPORTED_DATA,
            contracts.ResponseKind.UNSUPPORTED,
            id="unsupported data",
        ),
        pytest.param(
            contracts.NonAnswerReasonCode.UNSUPPORTED_FILTER,
            contracts.ResponseKind.UNSUPPORTED,
            id="unsupported filter",
        ),
        pytest.param(
            contracts.NonAnswerReasonCode.UNSUPPORTED_INTENT,
            contracts.ResponseKind.UNSUPPORTED,
            id="unsupported intent",
        ),
        pytest.param(
            contracts.NonAnswerReasonCode.UNSUPPORTED_SHAPE,
            contracts.ResponseKind.UNSUPPORTED,
            id="unsupported shape",
        ),
    ],
)
def test_response_kind_for_classifies_every_non_answer_reason(
    reason_code: contracts.NonAnswerReasonCode,
    expected_response_kind: contracts.ResponseKind,
) -> None:
    assert non_answer_catalog.response_kind_for(reason_code) == expected_response_kind

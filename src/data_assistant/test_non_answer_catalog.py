import pytest

import data_assistant.non_answer_catalog as non_answer_catalog
import data_assistant.workflow.contracts as contracts


@pytest.mark.parametrize(
    ("reason_code", "response_kind", "reason", "unresolved_ambiguities", "next_step"),
    [
        pytest.param(
            contracts.NonAnswerReasonCode.ACCESS_DENIED,
            contracts.ResponseKind.ACCESS_DENIAL,
            "",
            (),
            "Ask a data owner to grant Dataset Access or ask about available data.",
            id="access_denied",
        ),
        pytest.param(
            contracts.NonAnswerReasonCode.AMBIGUOUS_DATASET,
            contracts.ResponseKind.CLARIFICATION_NEEDED,
            "Multiple Curated Datasets match the Question Frame.",
            ("curated dataset",),
            "Ask which Curated Dataset should be used.",
            id="ambiguous_dataset",
        ),
        pytest.param(
            contracts.NonAnswerReasonCode.AMBIGUOUS_TABLE,
            contracts.ResponseKind.CLARIFICATION_NEEDED,
            "Multiple Dataset Tables can satisfy the Question Frame.",
            ("dataset table",),
            "Ask which Dataset Table should be used.",
            id="ambiguous_table",
        ),
        pytest.param(
            contracts.NonAnswerReasonCode.INVALID_PROVIDER_OUTPUT,
            contracts.ResponseKind.UNSUPPORTED,
            "The Question Interpreter provider returned invalid output.",
            ("provider output",),
            "Fix the provider contract before retrying.",
            id="invalid_provider_output",
        ),
        pytest.param(
            contracts.NonAnswerReasonCode.MISSING_REQUIRED_FIELD,
            contracts.ResponseKind.CLARIFICATION_NEEDED,
            "The Data Question is missing required interpretation details.",
            (),
            "Ask a clarification question before selecting data.",
            id="missing_required_field",
        ),
        pytest.param(
            contracts.NonAnswerReasonCode.NO_MATCHING_DATASET,
            contracts.ResponseKind.UNSUPPORTED,
            "No Curated Dataset safely matches the Question Frame.",
            ("curated dataset",),
            "Ask which approved business data should be used.",
            id="no_matching_dataset",
        ),
        pytest.param(
            contracts.NonAnswerReasonCode.NO_MATCHING_TABLE,
            contracts.ResponseKind.UNSUPPORTED,
            "No Dataset Table can satisfy the Question Frame.",
            ("dataset table",),
            "Ask which table-level metric or dimension should be used.",
            id="no_matching_table",
        ),
        pytest.param(
            contracts.NonAnswerReasonCode.PROVIDER_FAILURE,
            contracts.ResponseKind.UNSUPPORTED,
            "The Question Interpreter provider could not produce a proposal.",
            ("provider failure",),
            "Retry after the provider is available again.",
            id="provider_failure",
        ),
        pytest.param(
            contracts.NonAnswerReasonCode.UNKNOWN_SEMANTIC_LABEL,
            contracts.ResponseKind.UNSUPPORTED,
            "The Data Assistant could not match the requested Semantic Layer labels.",
            (),
            "Use exact Semantic Layer metric and dimension labels.",
            id="unknown_semantic_label",
        ),
        pytest.param(
            contracts.NonAnswerReasonCode.UNSUPPORTED_DATA,
            contracts.ResponseKind.UNSUPPORTED,
            "User-provided CSV files are not supported data sources.",
            ("unsupported data",),
            "Ask about an approved Curated Dataset in the Semantic Layer instead.",
            id="unsupported_data",
        ),
        pytest.param(
            contracts.NonAnswerReasonCode.UNSUPPORTED_FILTER,
            contracts.ResponseKind.UNSUPPORTED,
            "The Data Assistant does not support that filter yet.",
            ("supported filter",),
            "Use only supported filters for approved Semantic Fields.",
            id="unsupported_filter",
        ),
        pytest.param(
            contracts.NonAnswerReasonCode.UNSUPPORTED_FIELD_OPERATION,
            contracts.ResponseKind.UNSUPPORTED,
            "The Semantic Layer does not allow that operation for the field.",
            ("semantic field operation",),
            "Use only operations listed for the Semantic Field.",
            id="unsupported_field_operation",
        ),
        pytest.param(
            contracts.NonAnswerReasonCode.UNSUPPORTED_INTENT,
            contracts.ResponseKind.UNSUPPORTED,
            "The Data Assistant does not support that Data Question intent yet.",
            ("supported intent",),
            "Ask: What was total revenue by region in January 2026?",
            id="unsupported_intent",
        ),
        pytest.param(
            contracts.NonAnswerReasonCode.UNSUPPORTED_SHAPE,
            contracts.ResponseKind.UNSUPPORTED,
            "The Data Assistant cannot handle that Question Frame shape yet.",
            ("question shape",),
            "Ask for one grouping field or a scalar aggregate.",
            id="unsupported_shape",
        ),
    ],
)
def test_non_answer_catalog_defines_canonical_metadata(
    reason_code: contracts.NonAnswerReasonCode,
    response_kind: contracts.ResponseKind,
    reason: str,
    unresolved_ambiguities: tuple[str, ...],
    next_step: str,
) -> None:
    assert non_answer_catalog.response_kind_for(reason_code) == response_kind
    definition = non_answer_catalog._DEFINITIONS[reason_code]  # pyright: ignore[reportPrivateUsage]
    assert definition.reason == reason
    assert definition.unresolved_ambiguities == unresolved_ambiguities
    assert definition.next_step == next_step


def test_non_answer_catalog_builds_static_non_answer() -> None:
    result = non_answer_catalog.non_answer(
        contracts.NonAnswerReasonCode.NO_MATCHING_DATASET,
        stage=contracts.NonAnswerStage.SEMANTIC_ROUTER,
    )

    assert result == contracts.NonAnswer(
        stage=contracts.NonAnswerStage.SEMANTIC_ROUTER,
        reason_code=contracts.NonAnswerReasonCode.NO_MATCHING_DATASET,
        reason="No Curated Dataset safely matches the Question Frame.",
        unresolved_ambiguities=("curated dataset",),
        next_step="Ask which approved business data should be used.",
    )


def test_non_answer_catalog_builds_access_denied_non_answer() -> None:
    result = non_answer_catalog.access_denied_non_answer(
        "commerce",
        stage=contracts.NonAnswerStage.ACCESS_CONTROLLER,
    )

    assert result == contracts.NonAnswer(
        stage=contracts.NonAnswerStage.ACCESS_CONTROLLER,
        reason_code=contracts.NonAnswerReasonCode.ACCESS_DENIED,
        reason="You do not have access to the commerce Curated Dataset.",
        unresolved_ambiguities=(),
        next_step=(
            "Ask a data owner to grant Dataset Access or ask about available data."
        ),
        datasets=("commerce",),
    )


def test_non_answer_catalog_builds_missing_required_field_non_answer() -> None:
    result = non_answer_catalog.missing_required_field_non_answer(
        "metric",
        stage=contracts.NonAnswerStage.QUESTION_INTERPRETER,
    )

    assert result == contracts.NonAnswer(
        stage=contracts.NonAnswerStage.QUESTION_INTERPRETER,
        reason_code=contracts.NonAnswerReasonCode.MISSING_REQUIRED_FIELD,
        reason="The Data Question is missing required interpretation details.",
        unresolved_ambiguities=("metric",),
        next_step="Ask a clarification question before selecting data.",
    )


def test_non_answer_catalog_builds_unknown_semantic_label_non_answer() -> None:
    result = non_answer_catalog.unknown_semantic_label_non_answer(
        "field",
        stage=contracts.NonAnswerStage.DATA_REQUESTER,
    )

    assert result == contracts.NonAnswer(
        stage=contracts.NonAnswerStage.DATA_REQUESTER,
        reason_code=contracts.NonAnswerReasonCode.UNKNOWN_SEMANTIC_LABEL,
        reason=(
            "The Data Assistant could not match the requested Semantic Layer "
            "labels."
        ),
        unresolved_ambiguities=("field",),
        next_step="Use exact Semantic Layer metric and dimension labels.",
    )

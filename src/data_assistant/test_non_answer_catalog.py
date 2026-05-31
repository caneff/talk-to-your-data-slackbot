"""Tests for the canonical non-answer catalog.

These tests verify the catalog's *behavior* and *structural invariants* rather
than restating its copy. The reason/next_step strings live in the catalog's
definitions; duplicating them here would only catch accidental edits (by forcing
a second edit), not real regressions. Instead we assert completeness across
every reason code and the runtime logic of the context-aware builders.
"""

import pytest

import data_assistant.non_answer_catalog as non_answer_catalog
import data_assistant.workflow.contracts as contracts

_STAGE = contracts.NonAnswerStage.QUESTION_INTERPRETER

# Reason codes whose builders weave runtime context (a dataset or field name)
# into the non-answer instead of emitting the static catalog definition
# verbatim. Every other code is served by the generic ``non_answer`` builder.
_CONTEXTUAL_REASON_CODES = frozenset(
    {
        contracts.NonAnswerReasonCode.ACCESS_DENIED,
        contracts.NonAnswerReasonCode.MISSING_REQUIRED_FIELD,
        contracts.NonAnswerReasonCode.UNKNOWN_SEMANTIC_LABEL,
    }
)

_STATIC_REASON_CODES = [
    code
    for code in contracts.NonAnswerReasonCode
    if code not in _CONTEXTUAL_REASON_CODES
]


def _by_name(reason_code: contracts.NonAnswerReasonCode) -> str:
    return reason_code.name


@pytest.mark.parametrize(
    "reason_code", list(contracts.NonAnswerReasonCode), ids=_by_name
)
def test_every_reason_code_has_a_response_kind(
    reason_code: contracts.NonAnswerReasonCode,
) -> None:
    """Adding a reason code without a catalog entry should fail here."""
    assert isinstance(
        non_answer_catalog.response_kind_for(reason_code), contracts.ResponseKind
    )


@pytest.mark.parametrize("reason_code", _STATIC_REASON_CODES, ids=_by_name)
def test_static_builder_emits_a_complete_non_answer(
    reason_code: contracts.NonAnswerReasonCode,
) -> None:
    """The generic builder wires a fully-populated non-answer onto the stage."""
    result = non_answer_catalog.non_answer(reason_code, stage=_STAGE)  # type: ignore[arg-type]

    assert result.stage == _STAGE
    assert result.reason_code == reason_code
    assert result.reason, "static reason codes carry a fixed explanation"
    assert result.next_step, "every reason code needs an actionable next step"
    assert result.datasets == ()


def test_access_denied_builder_names_the_dataset() -> None:
    result = non_answer_catalog.access_denied_non_answer("commerce", stage=_STAGE)

    assert result.stage == _STAGE
    assert result.reason_code == contracts.NonAnswerReasonCode.ACCESS_DENIED
    assert result.reason == "You do not have access to the commerce Curated Dataset."
    assert result.datasets == ("commerce",)
    assert (
        non_answer_catalog.response_kind_for(result.reason_code)
        == contracts.ResponseKind.ACCESS_DENIAL
    )


def test_missing_required_field_builder_records_the_field() -> None:
    result = non_answer_catalog.missing_required_field_non_answer(
        "metric", stage=_STAGE
    )

    assert result.stage == _STAGE
    assert result.reason_code == contracts.NonAnswerReasonCode.MISSING_REQUIRED_FIELD
    assert result.unresolved_ambiguities == ("metric",)
    assert result.next_step
    assert (
        non_answer_catalog.response_kind_for(result.reason_code)
        == contracts.ResponseKind.CLARIFICATION_NEEDED
    )


def test_unknown_semantic_label_builder_records_the_label() -> None:
    result = non_answer_catalog.unknown_semantic_label_non_answer(
        "field", stage=_STAGE
    )

    assert result.stage == _STAGE
    assert result.reason_code == contracts.NonAnswerReasonCode.UNKNOWN_SEMANTIC_LABEL
    assert result.unresolved_ambiguities == ("field",)
    assert result.next_step
    assert (
        non_answer_catalog.response_kind_for(result.reason_code)
        == contracts.ResponseKind.UNSUPPORTED
    )

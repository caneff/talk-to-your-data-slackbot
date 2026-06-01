"""Tests for the canonical non-answer catalog.

These split into two concerns:

* **Structure** — every reason code classifies, and each builder produces the
  right structured ``NonAnswer`` (reason code, stage, context). These never
  mention user-facing copy.
* **Copy** — one golden test pins the exact rendered ``reason``/``next_step``
  strings. This is the single source of truth for Non-Answer wording; it is the
  intended failure when copy changes (see ADR-0007).
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
def test_static_builder_produces_structured_non_answer(
    reason_code: contracts.NonAnswerReasonCode,
) -> None:
    """The generic builder wires the reason code onto the requested stage."""
    result = non_answer_catalog.non_answer(reason_code, stage=_STAGE)  # type: ignore[arg-type]

    assert result.stage == _STAGE
    assert result.reason_code == reason_code
    assert result.datasets == ()


def test_access_denied_builder_names_the_dataset() -> None:
    result = non_answer_catalog.access_denied_non_answer("commerce", stage=_STAGE)

    assert result.stage == _STAGE
    assert result.reason_code == contracts.NonAnswerReasonCode.ACCESS_DENIED
    assert result.datasets == ("commerce",)


def test_missing_required_field_builder_records_the_field() -> None:
    result = non_answer_catalog.missing_required_field_non_answer(
        "metric", stage=_STAGE
    )

    assert result.stage == _STAGE
    assert result.reason_code == contracts.NonAnswerReasonCode.MISSING_REQUIRED_FIELD
    assert result.context == ("metric",)


def test_unknown_semantic_label_builder_records_the_label() -> None:
    result = non_answer_catalog.unknown_semantic_label_non_answer("field", stage=_STAGE)

    assert result.stage == _STAGE
    assert result.reason_code == contracts.NonAnswerReasonCode.UNKNOWN_SEMANTIC_LABEL
    assert result.context == ("field",)


# Golden copy. This is the ONE place exact user-facing Non-Answer wording is
# pinned; literals are intentional here. Each case renders through the same path
# the Response Composer uses. ``access_denied`` is built with a dataset so its
# template interpolates.
_GOLDEN_WORDING: tuple[
    tuple[contracts.NonAnswer, non_answer_catalog.NonAnswerWording], ...
] = (
    (
        non_answer_catalog.access_denied_non_answer("commerce", stage=_STAGE),
        non_answer_catalog.NonAnswerWording(
            reason="You do not have access to the commerce Curated Dataset.",
            next_step=(
                "Ask a data owner to grant Dataset Access or ask about available data."
            ),
        ),
    ),
    (
        non_answer_catalog.missing_required_field_non_answer("metric", stage=_STAGE),
        non_answer_catalog.NonAnswerWording(
            reason="The Data Question is missing required interpretation details.",
            next_step="Ask a clarification question before selecting data.",
        ),
    ),
    (
        non_answer_catalog.unknown_semantic_label_non_answer("field", stage=_STAGE),
        non_answer_catalog.NonAnswerWording(
            reason=(
                "The Data Assistant could not match the requested Semantic Layer "
                "labels."
            ),
            next_step="Use exact Semantic Layer metric and dimension labels.",
        ),
    ),
    (
        non_answer_catalog.non_answer(
            contracts.NonAnswerReasonCode.AMBIGUOUS_DATASET, stage=_STAGE
        ),
        non_answer_catalog.NonAnswerWording(
            reason="Multiple Curated Datasets match the Question Frame.",
            next_step="Ask which Curated Dataset should be used.",
        ),
    ),
    (
        non_answer_catalog.non_answer(
            contracts.NonAnswerReasonCode.AMBIGUOUS_TABLE, stage=_STAGE
        ),
        non_answer_catalog.NonAnswerWording(
            reason="Multiple Dataset Tables can satisfy the Question Frame.",
            next_step="Ask which Dataset Table should be used.",
        ),
    ),
    (
        non_answer_catalog.non_answer(
            contracts.NonAnswerReasonCode.INVALID_PROVIDER_OUTPUT, stage=_STAGE
        ),
        non_answer_catalog.NonAnswerWording(
            reason="The Question Interpreter provider returned invalid output.",
            next_step="Fix the provider contract before retrying.",
        ),
    ),
    (
        non_answer_catalog.non_answer(
            contracts.NonAnswerReasonCode.MISSING_TIME_SCOPE, stage=_STAGE
        ),
        non_answer_catalog.NonAnswerWording(
            reason=(
                "The Data Question must specify a time period or explicitly ask "
                "for all time."
            ),
            next_step="Ask which time period should be used, or confirm all time.",
        ),
    ),
    (
        non_answer_catalog.non_answer(
            contracts.NonAnswerReasonCode.NO_MATCHING_DATASET, stage=_STAGE
        ),
        non_answer_catalog.NonAnswerWording(
            reason="No Curated Dataset safely matches the Question Frame.",
            next_step="Ask which approved business data should be used.",
        ),
    ),
    (
        non_answer_catalog.non_answer(
            contracts.NonAnswerReasonCode.NO_MATCHING_TABLE, stage=_STAGE
        ),
        non_answer_catalog.NonAnswerWording(
            reason="No Dataset Table can satisfy the Question Frame.",
            next_step="Ask which table-level metric or dimension should be used.",
        ),
    ),
    (
        non_answer_catalog.non_answer(
            contracts.NonAnswerReasonCode.PROVIDER_FAILURE, stage=_STAGE
        ),
        non_answer_catalog.NonAnswerWording(
            reason="The Question Interpreter provider could not produce a proposal.",
            next_step="Retry after the provider is available again.",
        ),
    ),
    (
        non_answer_catalog.non_answer(
            contracts.NonAnswerReasonCode.UNSUPPORTED_DATA, stage=_STAGE
        ),
        non_answer_catalog.NonAnswerWording(
            reason="User-provided CSV files are not supported data sources.",
            next_step=(
                "Ask about an approved Curated Dataset in the Semantic Layer instead."
            ),
        ),
    ),
    (
        non_answer_catalog.non_answer(
            contracts.NonAnswerReasonCode.UNSUPPORTED_FILTER, stage=_STAGE
        ),
        non_answer_catalog.NonAnswerWording(
            reason="The Data Assistant does not support that filter yet.",
            next_step="Use only supported filters for approved Semantic Fields.",
        ),
    ),
    (
        non_answer_catalog.non_answer(
            contracts.NonAnswerReasonCode.UNSUPPORTED_FIELD_OPERATION, stage=_STAGE
        ),
        non_answer_catalog.NonAnswerWording(
            reason="The Semantic Layer does not allow that operation for the field.",
            next_step="Use only operations listed for the Semantic Field.",
        ),
    ),
    (
        non_answer_catalog.non_answer(
            contracts.NonAnswerReasonCode.UNSUPPORTED_INTENT, stage=_STAGE
        ),
        non_answer_catalog.NonAnswerWording(
            reason=(
                "The Data Assistant does not support that Data Question intent yet."
            ),
            next_step=(
                "Ask: What was total revenue by region in January 2026? "
                "Or: What was customer count by customer region in January 2026?"
            ),
        ),
    ),
    (
        non_answer_catalog.non_answer(
            contracts.NonAnswerReasonCode.UNSUPPORTED_SHAPE, stage=_STAGE
        ),
        non_answer_catalog.NonAnswerWording(
            reason="The Data Assistant cannot handle that Question Frame shape yet.",
            next_step="Ask for one grouping field or a scalar aggregate.",
        ),
    ),
)


def test_golden_wording_covers_every_reason_code() -> None:
    """Guard against a reason code slipping past the golden copy test."""
    covered = {non_answer.reason_code for non_answer, _ in _GOLDEN_WORDING}
    assert covered == set(contracts.NonAnswerReasonCode)


@pytest.mark.parametrize(
    ("non_answer", "expected"),
    _GOLDEN_WORDING,
    ids=[non_answer.reason_code.name for non_answer, _ in _GOLDEN_WORDING],
)
def test_render_wording_matches_golden_copy(
    non_answer: contracts.NonAnswer,
    expected: non_answer_catalog.NonAnswerWording,
) -> None:
    assert non_answer_catalog.render_wording(non_answer) == expected

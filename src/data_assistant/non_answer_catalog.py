"""Canonical non-answer classification helpers."""

from __future__ import annotations

from typing import assert_never

import data_assistant.workflow.contracts as contracts


def response_kind_for(
    reason_code: contracts.NonAnswerReasonCode,
) -> contracts.ResponseKind:
    """Return canonical response kind for a non-answer reason code."""
    match reason_code:
        case contracts.NonAnswerReasonCode.ACCESS_DENIED:
            return contracts.ResponseKind.ACCESS_DENIAL
        case (
            contracts.NonAnswerReasonCode.MISSING_REQUIRED_FIELD
            | contracts.NonAnswerReasonCode.AMBIGUOUS_DATASET
            | contracts.NonAnswerReasonCode.AMBIGUOUS_TABLE
        ):
            return contracts.ResponseKind.CLARIFICATION_NEEDED
        case (
            contracts.NonAnswerReasonCode.INVALID_PROVIDER_OUTPUT
            | contracts.NonAnswerReasonCode.NO_MATCHING_DATASET
            | contracts.NonAnswerReasonCode.NO_MATCHING_TABLE
            | contracts.NonAnswerReasonCode.PROVIDER_FAILURE
            | contracts.NonAnswerReasonCode.UNKNOWN_SEMANTIC_LABEL
            | contracts.NonAnswerReasonCode.UNSUPPORTED_DATA
            | contracts.NonAnswerReasonCode.UNSUPPORTED_FIELD_OPERATION
            | contracts.NonAnswerReasonCode.UNSUPPORTED_FILTER
            | contracts.NonAnswerReasonCode.UNSUPPORTED_INTENT
            | contracts.NonAnswerReasonCode.UNSUPPORTED_SHAPE
        ):
            return contracts.ResponseKind.UNSUPPORTED
        case _:
            assert_never(reason_code)

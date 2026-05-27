"""Shared guardrails for Question Interpreter implementations."""

from __future__ import annotations

import re

import data_assistant.workflow.contracts as contracts

_UNSUPPORTED_DATA_PATTERNS = (
    re.compile(r"\bcsv\b"),
    re.compile(r"\bupload\b"),
    re.compile(r"\bspreadsheet\b"),
    re.compile(r"\bsql\b"),
    re.compile(r"\btable\b"),
    re.compile(r"\bdatabase\b"),
)
_UNSUPPORTED_DATA_REASON = "User-provided CSV files are not supported data sources."
_UNSUPPORTED_DATA_NEXT_STEP = (
    "Ask about an approved Curated Dataset in the Semantic Layer instead."
)


def normalize_question(question: str) -> str:
    """Normalize question text for lightweight guard checks."""
    return " ".join(question.casefold().strip().split())


def mentions_unsupported_data(normalized_question: str) -> bool:
    """Return whether question text asks for unsupported data sources."""
    return any(
        pattern.search(normalized_question)
        for pattern in _UNSUPPORTED_DATA_PATTERNS
    )


def unsupported_data_non_answer() -> contracts.NonAnswer:
    """Return the shared NonAnswer for user-provided data requests."""
    return contracts.NonAnswer(
        stage=contracts.NonAnswerStage.QUESTION_INTERPRETER,
        reason_code=contracts.NonAnswerReasonCode.UNSUPPORTED_DATA,
        reason=_UNSUPPORTED_DATA_REASON,
        unresolved_ambiguities=("unsupported data",),
        next_step=_UNSUPPORTED_DATA_NEXT_STEP,
    )

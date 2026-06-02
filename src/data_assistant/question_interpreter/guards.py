"""Shared guardrails for Question Interpreter implementations."""

from __future__ import annotations

import re

_UNSUPPORTED_DATA_PATTERNS = (
    re.compile(r"\bcsv\b"),
    re.compile(r"\bupload\b"),
    re.compile(r"\bspreadsheet\b"),
    re.compile(r"\bsql\b"),
    re.compile(r"\btable\b"),
    re.compile(r"\bdatabase\b"),
)
_RANK_INTENT_PATTERNS = (
    re.compile(r"\btop\b"),
    re.compile(r"\bbottom\b"),
    re.compile(r"\bhighest\b"),
    re.compile(r"\blowest\b"),
    re.compile(r"\bbiggest\b"),
    re.compile(r"\bsmallest\b"),
    re.compile(
        r"\bmost\s+(?:total\s+)?(?:money|revenue|sales|customers?|orders?|"
        r"customer\s+count|order\s+count)\b"
    ),
    re.compile(
        r"\bleast\s+(?:total\s+)?(?:money|revenue|sales|customers?|orders?|"
        r"customer\s+count|order\s+count)\b"
    ),
)
# Coverage/existence phrasing ("what data do you have", "which months have
# data") asks what data exists rather than for a metric. These must fire only
# on that existence shape, never on the bare word "data" inside a metric
# question (e.g. "what was revenue data by region in January 2026?").
_AVAILABILITY_INTENT_PATTERNS = (
    re.compile(r"\b(?:what|which)\b.*\bhave\b.*\bdata\b"),
    re.compile(r"\bwhat\s+data\s+(?:do|does|is|are|exists?|available)\b"),
    re.compile(r"\bdo\s+you\s+have\b.*\bdata\b"),
)


def normalize_question(question: str) -> str:
    """Normalize question text for lightweight guard checks."""
    return " ".join(question.casefold().strip().split())


def mentions_unsupported_data(normalized_question: str) -> bool:
    """Return whether question text asks for unsupported data sources."""
    return any(
        pattern.search(normalized_question) for pattern in _UNSUPPORTED_DATA_PATTERNS
    )


def mentions_rank_intent(normalized_question: str) -> bool:
    """Return whether question text asks for top/bottom ranked results."""
    return any(pattern.search(normalized_question) for pattern in _RANK_INTENT_PATTERNS)


def mentions_availability_intent(normalized_question: str) -> bool:
    """Return whether question text asks which data or periods exist."""
    return any(
        pattern.search(normalized_question)
        for pattern in _AVAILABILITY_INTENT_PATTERNS
    )

"""QA battery markdown parsing for the Slack QA driver (#202).

A pure leaf module: it maps the curated QA battery markdown
(``docs/qa-retail-questions.md``) to a list of :class:`QACase` records. No
Slack, no OpenAI, no sidecar -- just ``re`` over the markdown. The Slack QA
driver (and the Known QA Issue preflight in ``preflight``) consume the
parsed cases; nothing here imports either sibling, so there is no cycle.

Headings (``#``), prose, and **indented** sub-bullets (``  - `` / ``\\t- ``)
are maintainer reference only -- they are never returned (the human is the
only oracle, so there is deliberately no expected-answer comparison here).
"""

from __future__ import annotations

import dataclasses
import re
import typing

_IDENTIFIED_CASE_PATTERN: typing.Final[re.Pattern[str]] = re.compile(
    r"^\[(?P<id>[^\]]+)\]\s+(?P<question>.+)$"
)


@dataclasses.dataclass(frozen=True)
class QACase:
    id: str | None
    question: str


def parse_battery_cases(
    markdown: str,
    *,
    allow_unidentified: bool = False,
) -> list[QACase]:
    """Extract top-level QA cases from markdown in source order."""
    cases: list[QACase] = []
    seen_ids: set[str] = set()
    for line in markdown.splitlines():
        if not line.startswith("- "):
            continue
        bullet_text = line[len("- ") :].strip()
        match = _IDENTIFIED_CASE_PATTERN.match(bullet_text)
        if match is None:
            if allow_unidentified:
                cases.append(QACase(id=None, question=bullet_text))
                continue
            raise ValueError(
                "Missing QA case id for bullet: "
                f"{bullet_text}. Use '- [qa-case-id] Question text' or pass "
                "--allow-unidentified-cases."
            )
        case_id = match.group("id").strip()
        if case_id in seen_ids:
            raise ValueError(f"Duplicate QA case id: {case_id}")
        seen_ids.add(case_id)
        cases.append(QACase(id=case_id, question=match.group("question").strip()))
    return cases


def parse_battery(markdown: str) -> list[str]:
    """Extract the top-level ``- `` bullets from the QA battery markdown.

    Every line matching ``^- `` is a question to send; the bullet marker is
    stripped and surrounding whitespace trimmed. Headings (``#``), prose, and
    **indented** sub-bullets (``  - `` / ``\\t- ``) are maintainer reference only
    -- they are never sent and never auto-checked (the human is the only oracle,
    so there is deliberately no expected-answer comparison here). Pure string ->
    list: no Slack, no OpenAI.
    """
    return [
        case.question for case in parse_battery_cases(markdown, allow_unidentified=True)
    ]

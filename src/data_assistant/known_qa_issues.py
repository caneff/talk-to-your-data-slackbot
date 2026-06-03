"""Known QA Issue sidecar loading, validation, pruning, and serialization."""

from __future__ import annotations

import dataclasses
import json
import pathlib
import typing

import data_assistant.interaction_log as interaction_log

SIDE_CAR_VERSION: typing.Final[int] = 1
VALID_FLAG_CATEGORIES: typing.Final[tuple[str, ...]] = interaction_log.FLAG_VOCABULARY
_ALLOWED_TOP_LEVEL_FIELDS: typing.Final[frozenset[str]] = frozenset(
    {"version", "questions"}
)
_ALLOWED_ENTRY_FIELDS: typing.Final[frozenset[str]] = frozenset(
    {"issue_number", "flag_category"}
)


@dataclasses.dataclass(frozen=True)
class KnownQAIssue:
    issue_number: int
    flag_category: str


@dataclasses.dataclass(frozen=True)
class KnownQAIssueSidecar:
    version: int
    questions: dict[str, list[KnownQAIssue]]


class KnownQAIssuePruneError(RuntimeError):
    """Raised when issue-state lookup fails during preflight pruning."""


def default_sidecar_path(battery_path: pathlib.Path) -> pathlib.Path:
    """Derive the default sidecar path from the markdown battery path."""
    return battery_path.with_suffix(".known-issues.json")


def load_sidecar(
    path: pathlib.Path,
    *,
    valid_case_ids: typing.Iterable[str],
    create_if_missing: bool = False,
) -> KnownQAIssueSidecar:
    """Load one sidecar file, optionally creating an empty v1 file first."""
    if create_if_missing and not path.exists():
        sidecar = KnownQAIssueSidecar(version=SIDE_CAR_VERSION, questions={})
        write_sidecar(path, sidecar)
        return sidecar
    raw_payload = json.loads(path.read_text(encoding="utf-8"))
    return _validate_sidecar(raw_payload, valid_case_ids=valid_case_ids)


def serialize_sidecar(sidecar: KnownQAIssueSidecar) -> str:
    """Return deterministic JSON for the committed sidecar file."""
    payload = {
        "version": sidecar.version,
        "questions": {
            question_id: [
                {
                    "issue_number": issue.issue_number,
                    "flag_category": issue.flag_category,
                }
                for issue in sorted(
                    issues,
                    key=lambda item: (item.issue_number, item.flag_category),
                )
            ]
            for question_id, issues in sorted(sidecar.questions.items())
        },
    }
    return json.dumps(payload, indent=2) + "\n"


def write_sidecar(path: pathlib.Path, sidecar: KnownQAIssueSidecar) -> None:
    """Write one sidecar file with stable formatting."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(serialize_sidecar(sidecar), encoding="utf-8")


def prune_sidecar(
    sidecar: KnownQAIssueSidecar,
    *,
    valid_case_ids: typing.Iterable[str],
    is_issue_open: typing.Callable[[int], bool],
) -> KnownQAIssueSidecar:
    """Remove closed issues, stale case ids, and empty question keys."""
    valid_case_id_set = set(valid_case_ids)
    pruned_questions: dict[str, list[KnownQAIssue]] = {}
    for question_id, issues in sidecar.questions.items():
        if question_id not in valid_case_id_set:
            continue
        kept_issues: list[KnownQAIssue] = []
        for issue in issues:
            try:
                if is_issue_open(issue.issue_number):
                    kept_issues.append(issue)
            except Exception as exc:  # pragma: no cover - exact branch in tests
                raise KnownQAIssuePruneError(
                    "Failed to prune Known QA Issue sidecar for "
                    f"issue #{issue.issue_number}: {exc}"
                ) from exc
        if kept_issues:
            pruned_questions[question_id] = kept_issues
    return KnownQAIssueSidecar(version=sidecar.version, questions=pruned_questions)


def _validate_sidecar(
    payload: object,
    *,
    valid_case_ids: typing.Iterable[str],
) -> KnownQAIssueSidecar:
    if not isinstance(payload, dict):
        raise ValueError(
            "Malformed Known QA Issue sidecar: top-level JSON object required."
        )
    payload_map = typing.cast("dict[str, object]", payload)
    _reject_unknown_keys(
        payload_map,
        allowed_keys=_ALLOWED_TOP_LEVEL_FIELDS,
        error_prefix="Malformed Known QA Issue sidecar",
        field_noun="top-level field",
    )

    version = payload_map.get("version")
    if version != SIDE_CAR_VERSION:
        raise ValueError(
            "Unsupported Known QA Issue sidecar version: "
            f"{version!r}. Expected {SIDE_CAR_VERSION}."
        )

    questions = payload_map.get("questions")
    if not isinstance(questions, dict):
        raise ValueError(
            "Malformed Known QA Issue sidecar: 'questions' must be an object."
        )
    questions_map = typing.cast("dict[object, object]", questions)

    valid_case_id_set = set(valid_case_ids)
    parsed_questions: dict[str, list[KnownQAIssue]] = {}
    for question_id, raw_entries in questions_map.items():
        if not isinstance(question_id, str):
            raise ValueError(
                "Malformed Known QA Issue sidecar: question keys must be strings."
            )
        if question_id not in valid_case_id_set:
            raise ValueError(f"Unknown QA case id in sidecar: {question_id}")
        if not isinstance(raw_entries, list):
            raise ValueError(
                "Malformed Known QA Issue sidecar: question entries must be lists."
            )
        entry_list = typing.cast("list[object]", raw_entries)
        parsed_questions[question_id] = [
            _validate_issue_entry(entry, question_id=question_id)
            for entry in entry_list
        ]
    return KnownQAIssueSidecar(version=SIDE_CAR_VERSION, questions=parsed_questions)


def _validate_issue_entry(entry: object, *, question_id: str) -> KnownQAIssue:
    if not isinstance(entry, dict):
        raise ValueError(
            "Malformed Known QA Issue sidecar entry for "
            f"{question_id}: object required."
        )
    entry_map = typing.cast("dict[str, object]", entry)
    _reject_unknown_keys(
        entry_map,
        allowed_keys=_ALLOWED_ENTRY_FIELDS,
        error_prefix=f"Malformed Known QA Issue sidecar entry for {question_id}",
        field_noun="entry field",
    )

    issue_number = entry_map.get("issue_number")
    if not isinstance(issue_number, int) or issue_number <= 0:
        raise ValueError(
            "Malformed Known QA Issue sidecar entry for "
            f"{question_id}: issue_number must be a positive integer."
        )

    flag_category = entry_map.get("flag_category")
    if flag_category not in VALID_FLAG_CATEGORIES:
        raise ValueError(
            "Malformed Known QA Issue sidecar entry for "
            f"{question_id}: flag_category must be one of {VALID_FLAG_CATEGORIES}."
        )

    return KnownQAIssue(
        issue_number=issue_number,
        flag_category=typing.cast("str", flag_category),
    )


def _reject_unknown_keys(
    payload_map: dict[str, object],
    *,
    allowed_keys: frozenset[str],
    error_prefix: str,
    field_noun: str,
) -> None:
    unknown_keys = sorted(set(payload_map) - allowed_keys)
    if unknown_keys:
        raise ValueError(f"{error_prefix}: Unknown {field_noun} {unknown_keys[0]!r}.")

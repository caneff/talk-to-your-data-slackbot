"""Known QA Issue preflight orchestration for the Slack QA driver (#202).

This is the **preflight** subsystem: before the driver posts any Slack
message, it creates/validates the Known QA Issue sidecar for one battery,
checks each referenced GitHub issue's state, prunes entries whose issue has
closed, and rewrites the sidecar when it changed. The driver then uses the
returned :class:`PreflightKnownIssuesResult` to annotate or skip cases.

Note the name distinction (words reversed):

* ``known_qa_issues`` -- the JSONL sidecar **data store** (load/prune/write).
* ``qa_known_issues`` (this module) -- the **orchestration** that USES that
  store to run the preflight.

Dependency direction is one-way: this module imports ``qa_battery`` (for the
:class:`~data_assistant.qa_battery.QACase` type) and ``known_qa_issues`` (the
store); neither imports back, so there is no cycle.
"""

from __future__ import annotations

import collections.abc as collections_abc
import dataclasses
import json
import pathlib
import subprocess
import typing

import data_assistant.known_qa_issues as known_qa_issues
import data_assistant.qa_battery as qa_battery


@dataclasses.dataclass(frozen=True)
class PreflightKnownIssuesResult:
    known_issues_by_case_id: dict[str, tuple[known_qa_issues.KnownQAIssue, ...]]
    pruned_count: int


def resolve_known_issues_path(
    *,
    battery_path: pathlib.Path,
    known_issues_path: pathlib.Path | None,
) -> pathlib.Path:
    """Resolve the Known QA Issue sidecar path for one battery."""
    if known_issues_path is not None:
        return known_issues_path
    return known_qa_issues.default_sidecar_path(battery_path)


def preflight_known_issues(
    *,
    battery_path: pathlib.Path,
    cases: collections_abc.Sequence[qa_battery.QACase],
    known_issues_path: pathlib.Path | None,
    skip_prune: bool,
    is_issue_open: collections_abc.Callable[[int], bool] | None = None,
) -> PreflightKnownIssuesResult:
    """Create, validate, and optionally prune the Known QA Issue sidecar."""
    identified_case_ids = [case.id for case in cases if case.id is not None]
    if not identified_case_ids:
        return PreflightKnownIssuesResult(known_issues_by_case_id={}, pruned_count=0)
    if len(identified_case_ids) != len(cases):
        raise ValueError(
            "Mixed identified and unidentified QA cases: either give every "
            "battery question a '[qa-case-id]' or use only legacy "
            "unidentified bullets."
        )

    sidecar_path = resolve_known_issues_path(
        battery_path=battery_path,
        known_issues_path=known_issues_path,
    )
    sidecar_existed = sidecar_path.exists()
    case_ids = list(identified_case_ids)
    sidecar = known_qa_issues.load_sidecar(
        sidecar_path,
        valid_case_ids=case_ids,
        create_if_missing=True,
    )
    if skip_prune:
        return PreflightKnownIssuesResult(
            known_issues_by_case_id={
                case_id: tuple(issues) for case_id, issues in sidecar.questions.items()
            },
            pruned_count=0,
        )
    issue_is_open = is_issue_open or _github_issue_is_open
    open_issue_numbers: set[int] = set()
    for issue_number in known_qa_issues.issue_numbers(sidecar):
        try:
            if issue_is_open(issue_number):
                open_issue_numbers.add(issue_number)
        except Exception as exc:
            raise known_qa_issues.KnownQAIssuePruneError(
                "Failed to prune Known QA Issue sidecar for "
                f"issue #{issue_number}: {exc}"
            ) from exc
    pruned = known_qa_issues.prune_sidecar_using_open_issue_numbers(
        sidecar,
        valid_case_ids=case_ids,
        open_issue_numbers=open_issue_numbers,
    )
    pruned_count = sum(len(issues) for issues in sidecar.questions.values()) - sum(
        len(issues) for issues in pruned.questions.values()
    )
    if not sidecar_existed or pruned != sidecar:
        known_qa_issues.write_sidecar(sidecar_path, pruned)
    return PreflightKnownIssuesResult(
        known_issues_by_case_id={
            case_id: tuple(issues) for case_id, issues in pruned.questions.items()
        },
        pruned_count=pruned_count,
    )


def _github_issue_is_open(issue_number: int) -> bool:
    """Return whether one GitHub issue is still open via ``gh issue view``."""
    completed = subprocess.run(
        ["gh", "issue", "view", str(issue_number), "--json", "state"],
        capture_output=True,
        check=True,
        cwd=pathlib.Path(__file__).resolve().parents[2],
        text=True,
    )
    payload = typing.cast("dict[str, object]", json.loads(completed.stdout))
    return payload.get("state") == "OPEN"

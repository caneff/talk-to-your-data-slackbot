"""Record one Known QA Issue sidecar mapping for a confirmed QA Review flag.

Operator utility for the triage-flagged-interactions workflow: after a human
confirms a flagged QA Review case maps to a GitHub issue, this writes the
``(qa_case_id, issue_number, flag_category)`` entry into the battery's sidecar.

This is glue, not product: it lives in ``scripts/`` (kept out of the wheel) and
is a thin CLI over the already-tested helpers in
``data_assistant.known_qa_issues``. All three identifying flags are **required**
(no defaults) so a bogus entry cannot be written by accident.

The eligibility gate (``record_known_issue_for_qa_record``) silently no-ops on
an unknown case id or an ineligible record; this CLI surfaces that as a non-zero
exit and an explicit message instead of a silent unchanged sidecar.
"""

from __future__ import annotations

import argparse
import pathlib

from data_assistant import known_qa_issues
from data_assistant.slack_qa import battery, driver


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Record a confirmed QA-case-to-issue mapping in the sidecar."
    )
    parser.add_argument("--qa-case-id", required=True)
    parser.add_argument("--issue-number", required=True, type=int)
    parser.add_argument("--flag-category", required=True)
    parser.add_argument(
        "--battery-path",
        type=pathlib.Path,
        default=pathlib.Path(driver.DEFAULT_BATTERY_PATH),
        help=f"Markdown battery (default: {driver.DEFAULT_BATTERY_PATH}).",
    )
    args = parser.parse_args(argv)
    qa_case_id: str = args.qa_case_id
    issue_number: int = args.issue_number
    flag_category: str = args.flag_category
    battery_path: pathlib.Path = args.battery_path

    cases = battery.parse_battery_cases(battery_path.read_text(encoding="utf-8"))
    valid_case_ids = [case.id for case in cases if case.id is not None]

    sidecar_path = known_qa_issues.default_sidecar_path(battery_path)
    sidecar = known_qa_issues.load_sidecar(
        sidecar_path, valid_case_ids=valid_case_ids, create_if_missing=True
    )
    record = {"source": "qa_review", "qa_case_id": qa_case_id}
    updated = known_qa_issues.record_known_issue_for_qa_record(
        sidecar,
        record=record,
        issue_number=issue_number,
        flag_category=flag_category,
        valid_case_ids=valid_case_ids,
    )
    if updated is sidecar:
        print(
            f"no-op: {qa_case_id!r} is not an eligible/known QA case id; "
            "sidecar unchanged"
        )
        return 1
    known_qa_issues.write_sidecar(sidecar_path, updated)
    print(f"recorded ({qa_case_id}, {issue_number}, {flag_category}) -> {sidecar_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

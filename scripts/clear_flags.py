"""Clear handled flags from one or more Interaction Log records.

Operator utility for the triage-flagged-interactions workflow: empties each
record's ``flags`` list (the interaction line itself is kept) so handled flags
drop out of the flagged set and are not re-triaged.

This is glue, not product: it lives in ``scripts/`` (kept out of the wheel) and
is a thin CLI over ``data_assistant.interaction_log.clear_flags``. It takes any
number of ids -- the triage workflow clears *every* id handled in a session, so
one invocation replaces the per-id loop and prints a per-id result table
(``id<TAB>True/False``; True = a still-flagged record was found and emptied,
False = unknown id or already-unflagged).

``--log-path`` targets a specific log (e.g. ``/var/data/interactions.jsonl`` for
the hosted instance via a worker); it defaults to the local Interaction Log.
"""

from __future__ import annotations

import argparse
import pathlib

from data_assistant import interaction_log


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Clear handled flags from Interaction Log records by id."
    )
    parser.add_argument("ids", nargs="+", metavar="ID")
    parser.add_argument(
        "--log-path",
        type=pathlib.Path,
        default=interaction_log.DEFAULT_LOG_PATH,
        help="Interaction Log JSONL to rewrite (default: the local log).",
    )
    args = parser.parse_args(argv)
    ids: list[str] = args.ids
    log_path: pathlib.Path = args.log_path

    for interaction_id in ids:
        cleared = interaction_log.clear_flags(interaction_id, path=log_path)
        print(f"{interaction_id}\t{cleared}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

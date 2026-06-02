"""Local Interaction Log: append-only JSONL of Data Questions and responses.

This flat module owns ALL file I/O and the on-disk record schema for the
Interaction Log -- the local-dev consumer of the Decision Trail (see ADR-0016).
Every Data Question handled by the Slack Assistant Adapter writes ONE structured
JSON line here so a maintainer can paste any interaction into Claude Code when
asking for an improvement.

The log lives at a gitignored ``logs/interactions.jsonl`` under the repo root.
The path is injectable (``path`` argument) so tests write to ``tmp_path`` and
never touch the real log.

Sanitization (see ADR-0016 and CONTEXT.md): records carry the Question Frame,
prepared-data SHAPE (rows x columns) + quality notes, and the tiny ``key_data``
headline numbers -- but NEVER the bulk Prepared Data cell values and never
secrets. Building the sanitized record is the Adapter's job; this module only
serializes whatever flat dict it is handed.
"""

from __future__ import annotations

import json
import pathlib
import typing

# Repo-root-relative gitignored log location. ``interaction_log.py`` lives at
# ``<repo>/src/data_assistant/interaction_log.py``; the repo root is three
# parents up.
DEFAULT_LOG_PATH = (
    pathlib.Path(__file__).resolve().parents[2] / "logs" / "interactions.jsonl"
)

# Flag vocabulary for the Interaction Log. Defined here for Slice 2 (the Slack
# flag buttons, issue #111); this slice always writes ``flags == []``.
FLAG_VOCABULARY: typing.Final[tuple[str, ...]] = ("correctness", "formatting")

InteractionRecord: typing.TypeAlias = typing.Mapping[str, object]


def append_interaction(
    record: InteractionRecord,
    *,
    path: pathlib.Path = DEFAULT_LOG_PATH,
) -> str:
    """Append one interaction ``record`` as a single JSON line; return its id.

    Opens the log in append mode and writes exactly one ``json.dumps(record)``
    followed by a newline, so the file stays a greppable/diffable JSONL stream.
    The parent directory is created if missing. The record's ``id`` field is
    returned so callers can correlate the log line (Slice 2 will flag by id).
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record)
    with path.open("a", encoding="utf-8") as log_file:
        log_file.write(line + "\n")
    return str(record["id"])

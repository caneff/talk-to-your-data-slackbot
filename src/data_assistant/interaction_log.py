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

import contextlib
import json
import os
import pathlib
import tempfile
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


def flag_interaction(
    interaction_id: str,
    category: str,
    *,
    path: pathlib.Path = DEFAULT_LOG_PATH,
) -> bool:
    """Append ``category`` to one record's ``flags`` via an atomic rewrite.

    Slice 2 (issue #111): when a maintainer clicks a flag button on a Slack
    reply, the matching Interaction Log record (by ``id``) gets ``category``
    added to its ``flags`` list, **deduped** (set-union semantics; existing
    order preserved). Returns ``True`` when a record was found and updated,
    ``False`` when no record matches ``interaction_id`` (a no-op -- e.g. an id
    from an already-rotated log).

    ``category`` must be one of :data:`FLAG_VOCABULARY`; anything else is a
    programmer error (the action_id->category map is the single source of
    truth) and raises ``ValueError``.

    The rewrite is atomic: every line is written to a temp file in the SAME
    directory, then ``os.replace`` renames it over the original. The live log is
    never partially written. Concurrent writers are out of scope -- this is a
    single-process local dev tool, so there is no file locking.
    """
    if category not in FLAG_VOCABULARY:
        raise ValueError(
            f"Unknown flag category {category!r}; expected one of {FLAG_VOCABULARY}."
        )

    def _add_category(record: dict[str, typing.Any]) -> bool:
        flags = list(record.get("flags") or [])
        if category not in flags:
            flags.append(category)
        record["flags"] = flags
        return True

    return _rewrite_matching_record(path, interaction_id, _add_category)


def clear_flags(
    interaction_id: str,
    *,
    path: pathlib.Path = DEFAULT_LOG_PATH,
) -> bool:
    """Empty one record's ``flags`` list via the same atomic rewrite.

    Used by the triage workflow to mark a flagged interaction *handled*: once a
    fix or issue exists, clearing the flags drops the record out of the flagged
    set so it is not re-triaged, while the interaction line itself is **kept**
    (it stays useful as an improvement corpus -- this is not a delete).

    Returns ``True`` when a record with ``interaction_id`` that still had flags
    was found and emptied. Returns ``False`` (a no-op, no rewrite) when no record
    matches, the record already has no flags, or the file does not exist.
    """

    def _empty_flags(record: dict[str, typing.Any]) -> bool:
        if not record.get("flags"):
            return False
        record["flags"] = []
        return True

    return _rewrite_matching_record(path, interaction_id, _empty_flags)


def _rewrite_matching_record(
    path: pathlib.Path,
    interaction_id: str,
    mutate: typing.Callable[[dict[str, typing.Any]], bool],
) -> bool:
    """Atomically rewrite the log, applying ``mutate`` to the record by id.

    Walks every JSON line; for the record whose ``id`` matches, calls ``mutate``
    (which edits the record dict in place and returns whether it changed it). If
    any line changed, the whole file is rewritten via a temp file + ``os.replace``
    so the live log is never partially written. Returns whether anything changed;
    a missing file or no match is a ``False`` no-op. Concurrent writers are out
    of scope -- this is a single-process local dev tool, so there is no locking.
    """
    if not path.exists():
        return False

    lines = path.read_text(encoding="utf-8").splitlines()
    changed = False
    rewritten: list[str] = []
    for line in lines:
        if not line:
            rewritten.append(line)
            continue
        record = json.loads(line)
        if record.get("id") == interaction_id and mutate(record):
            changed = True
            rewritten.append(json.dumps(record))
        else:
            rewritten.append(line)

    if not changed:
        return False

    # Atomic in-place rewrite: temp file in the same directory, then rename.
    directory = path.parent
    fd, temp_name = tempfile.mkstemp(dir=directory, prefix=path.name, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as temp_file:
            for line in rewritten:
                temp_file.write(line + "\n")
        os.replace(temp_name, path)
    except BaseException:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(temp_name)
        raise
    return True

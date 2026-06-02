"""Local Interaction Log: retention-bounded JSONL of Data Questions and responses.

This flat module owns ALL file I/O and the on-disk record schema for the
Interaction Log -- the local-dev consumer of the Decision Trail (see ADR-0016).
Every Data Question handled by the Slack Assistant Adapter append-first writes
ONE structured JSON line here so a maintainer can paste retained interactions
into Claude Code when asking for an improvement.

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
import dataclasses
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

# Flag vocabulary for the Interaction Log. Defined here for the Slack flag
# buttons (issue #111); the ``investigate`` category was added in issue #123.
FLAG_VOCABULARY: typing.Final[tuple[str, ...]] = (
    "correctness",
    "formatting",
    "investigate",
)

InteractionRecord: typing.TypeAlias = typing.Mapping[str, object]


@dataclasses.dataclass(frozen=True)
class RetentionPolicy:
    """Byte-triggered retention settings for the local Interaction Log."""

    trigger_bytes: int
    target_bytes: int
    recent_unflagged_answer_limit: int


DEFAULT_RETENTION_POLICY: typing.Final[RetentionPolicy] = RetentionPolicy(
    trigger_bytes=100 * 1024 * 1024,
    target_bytes=50 * 1024 * 1024,
    recent_unflagged_answer_limit=5_000,
)


@dataclasses.dataclass(frozen=True)
class _LogLine:
    index: int
    text: str
    record: dict[str, object] | None

    @property
    def byte_count(self) -> int:
        return len(self.text.encode("utf-8")) + 1


def append_interaction(
    record: InteractionRecord,
    *,
    path: pathlib.Path = DEFAULT_LOG_PATH,
    retention_policy: RetentionPolicy = DEFAULT_RETENTION_POLICY,
) -> str:
    """Append one interaction ``record`` as a single JSON line; return its id.

    Opens the log in append mode and writes exactly one ``json.dumps(record)``
    followed by a newline, so normal writes stay cheap and greppable. The parent
    directory is created if missing. The record's ``id`` field is returned so
    callers can correlate the log line.

    Retention is checked after the append. If ``retention_policy`` is violated,
    this module atomically compacts the log before returning.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record)
    with path.open("a", encoding="utf-8") as log_file:
        log_file.write(line + "\n")
    enforce_retention(path=path, policy=retention_policy)
    return str(record["id"])


def flag_interaction(
    interaction_id: str,
    category: str,
    *,
    path: pathlib.Path = DEFAULT_LOG_PATH,
    retention_policy: RetentionPolicy = DEFAULT_RETENTION_POLICY,
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

    def _add_category(record: dict[str, object]) -> bool:
        flags = _record_flags(record)
        if category not in flags:
            flags.append(category)
        record["flags"] = flags
        return True

    return _rewrite_matching_record(
        path,
        interaction_id,
        _add_category,
        retention_policy=retention_policy,
    )


def clear_flags(
    interaction_id: str,
    *,
    path: pathlib.Path = DEFAULT_LOG_PATH,
    retention_policy: RetentionPolicy = DEFAULT_RETENTION_POLICY,
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

    def _empty_flags(record: dict[str, object]) -> bool:
        if not record.get("flags"):
            return False
        record["flags"] = []
        return True

    return _rewrite_matching_record(
        path,
        interaction_id,
        _empty_flags,
        retention_policy=retention_policy,
    )


def _rewrite_matching_record(
    path: pathlib.Path,
    interaction_id: str,
    mutate: typing.Callable[[dict[str, object]], bool],
    *,
    retention_policy: RetentionPolicy = DEFAULT_RETENTION_POLICY,
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

    lines = _read_log_lines(path)
    changed = False
    rewritten: list[str] = []
    for line in lines:
        if line.record is None:
            rewritten.append(line.text)
            continue
        record = line.record
        if record.get("id") == interaction_id and mutate(record):
            changed = True
            rewritten.append(json.dumps(record))
        else:
            rewritten.append(line.text)

    if not changed:
        return False

    _write_lines_atomic(path, rewritten)
    enforce_retention(path=path, policy=retention_policy)
    return True


def enforce_retention(
    *,
    path: pathlib.Path = DEFAULT_LOG_PATH,
    policy: RetentionPolicy = DEFAULT_RETENTION_POLICY,
) -> None:
    """Apply ``policy`` when the log exceeds its trigger size.

    Selection is priority-first, then newest-first inside each priority bucket;
    retained lines are written back in original chronological order. Malformed
    JSONL lines are retained as diagnosis signal when space allows.
    """
    if not path.exists() or path.stat().st_size <= policy.trigger_bytes:
        return

    lines = _read_log_lines(path)
    keepable_lines = _keepable_lines(lines, policy)
    retained: list[_LogLine] = []
    retained_bytes = 0
    for line in _priority_ordered(keepable_lines):
        if retained_bytes + line.byte_count <= policy.target_bytes:
            retained.append(line)
            retained_bytes += line.byte_count
        elif not retained:
            retained.append(line)
            break

    retained_indices = {line.index for line in retained}
    compacted = [line.text for line in lines if line.index in retained_indices]
    _write_lines_atomic(path, compacted)


def _read_log_lines(path: pathlib.Path) -> list[_LogLine]:
    lines: list[_LogLine] = []
    for index, text in enumerate(path.read_text(encoding="utf-8").splitlines()):
        try:
            parsed: object = json.loads(text)
        except json.JSONDecodeError:
            parsed = None
        record = (
            typing.cast(dict[str, object], parsed) if isinstance(parsed, dict) else None
        )
        lines.append(_LogLine(index=index, text=text, record=record))
    return lines


def _record_flags(record: dict[str, object]) -> list[object]:
    flags = record.get("flags")
    if not isinstance(flags, list):
        return []
    return list(typing.cast(list[object], flags))


def _keepable_lines(
    lines: list[_LogLine],
    policy: RetentionPolicy,
) -> list[_LogLine]:
    recent_answer_indices = _recent_unflagged_answer_indices(
        lines,
        policy.recent_unflagged_answer_limit,
    )
    return [
        line
        for line in lines
        if _line_priority(line) != _UNFLAGGED_ANSWER_PRIORITY
        or line.index in recent_answer_indices
    ]


def _recent_unflagged_answer_indices(
    lines: list[_LogLine],
    limit: int,
) -> set[int]:
    if limit <= 0:
        return set()
    answer_indices = [
        line.index
        for line in lines
        if _line_priority(line) == _UNFLAGGED_ANSWER_PRIORITY
    ]
    return set(answer_indices[-limit:])


_FLAGGED_PRIORITY: typing.Final[int] = 0
_ERROR_PRIORITY: typing.Final[int] = 1
_MALFORMED_PRIORITY: typing.Final[int] = 2
_NON_ANSWER_PRIORITY: typing.Final[int] = 3
_UNFLAGGED_ANSWER_PRIORITY: typing.Final[int] = 4


def _line_priority(line: _LogLine) -> int:
    record = line.record
    if record is None:
        return _MALFORMED_PRIORITY
    if record.get("flags"):
        return _FLAGGED_PRIORITY
    outcome = record.get("outcome")
    if outcome == "error":
        return _ERROR_PRIORITY
    if outcome == "non_answer":
        return _NON_ANSWER_PRIORITY
    if outcome == "answer":
        return _UNFLAGGED_ANSWER_PRIORITY
    return _MALFORMED_PRIORITY


def _priority_ordered(lines: list[_LogLine]) -> list[_LogLine]:
    return sorted(lines, key=lambda line: (_line_priority(line), -line.index))


def _write_lines_atomic(path: pathlib.Path, lines: list[str]) -> None:
    # Atomic in-place rewrite: temp file in the same directory, then rename.
    directory = path.parent
    fd, temp_name = tempfile.mkstemp(dir=directory, prefix=path.name, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as temp_file:
            for line in lines:
                temp_file.write(line + "\n")
        os.replace(temp_name, path)
    except BaseException:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(temp_name)
        raise

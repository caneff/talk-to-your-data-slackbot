"""Last-opened assistant thread pointer for the Slack QA driver (#128).

The Slack QA driver posts answers into an assistant thread as the bot. Rather
than make a maintainer copy the thread's ``channel`` + ``thread_ts`` by hand,
the running bot records them here on every ``assistant_thread_started`` event,
and the driver reads them back to auto-discover the most recently opened thread.

This is a tiny, last-writer-wins JSON file (``logs/last_assistant_thread.json``)
owning a single ``{"channel": ..., "thread_ts": ...}`` record. It is local-dev
state, gitignored alongside the Interaction Log, and the path is injectable so
tests write to ``tmp_path``. Reads NEVER raise on a missing or malformed file --
the driver treats "no usable pointer" the same as "no pointer", falling back to
its explicit ``--channel``/``--thread-ts`` overrides.
"""

from __future__ import annotations

import contextlib
import json
import os
import pathlib
import tempfile
import typing

# Repo-root-relative gitignored pointer location, alongside the Interaction Log.
# ``assistant_thread_pointer.py`` lives at
# ``<repo>/src/data_assistant/assistant_thread_pointer.py``; the repo root is
# three parents up.
DEFAULT_POINTER_PATH = (
    pathlib.Path(__file__).resolve().parents[2] / "logs" / "last_assistant_thread.json"
)


def write_latest(
    channel: str,
    thread_ts: str,
    *,
    path: pathlib.Path = DEFAULT_POINTER_PATH,
) -> None:
    """Atomically record the most recently opened assistant thread.

    Writes ``{"channel": channel, "thread_ts": thread_ts}`` as JSON via a temp
    file in the same directory + ``os.replace`` so the pointer is never left
    partially written. The parent directory is created if missing. Last writer
    wins: opening a new thread overwrites the prior pointer.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps({"channel": channel, "thread_ts": thread_ts})
    fd, temp_name = tempfile.mkstemp(dir=path.parent, prefix=path.name, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as temp_file:
            temp_file.write(payload)
        os.replace(temp_name, path)
    except BaseException:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(temp_name)
        raise


def read_latest(
    path: pathlib.Path = DEFAULT_POINTER_PATH,
) -> tuple[str, str] | None:
    """Return ``(channel, thread_ts)`` from the pointer, or ``None``.

    Returns ``None`` -- never raises -- when the file is missing, is not valid
    JSON, is not a JSON object, or lacks a string ``channel``/``thread_ts``. The
    caller treats every such case as "no usable pointer" and falls back to
    explicit overrides.
    """
    if not path.exists():
        return None
    try:
        parsed: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(parsed, dict):
        return None
    record = typing.cast("dict[str, object]", parsed)
    channel = record.get("channel")
    thread_ts = record.get("thread_ts")
    if isinstance(channel, str) and isinstance(thread_ts, str):
        return channel, thread_ts
    return None

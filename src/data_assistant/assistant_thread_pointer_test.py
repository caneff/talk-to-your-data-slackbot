"""Tests for the assistant-thread pointer (pure file I/O).

The pointer is the seam that lets the Slack QA driver auto-discover the most
recently opened assistant thread without a manual ``--channel``/``--thread-ts``
step: the running bot writes ``(channel, thread_ts)`` on ``thread_started`` and
the driver reads it back. These tests cover the round-trip and the two benign
failure modes (missing file, malformed JSON) -- no Slack, no OpenAI.
"""

from __future__ import annotations

import pathlib

import data_assistant.assistant_thread_pointer as assistant_thread_pointer


def test_write_then_read_round_trips(tmp_path: pathlib.Path) -> None:
    path = tmp_path / "last_assistant_thread.json"

    assistant_thread_pointer.write_latest("C123", "1748880000.123456", path=path)

    assert assistant_thread_pointer.read_latest(path) == ("C123", "1748880000.123456")


def test_write_latest_overwrites_last_writer_wins(tmp_path: pathlib.Path) -> None:
    path = tmp_path / "last_assistant_thread.json"

    assistant_thread_pointer.write_latest("C123", "1.1", path=path)
    assistant_thread_pointer.write_latest("C999", "2.2", path=path)

    # Last writer wins: only the most recently opened thread is retained.
    assert assistant_thread_pointer.read_latest(path) == ("C999", "2.2")


def test_read_latest_missing_file_returns_none(tmp_path: pathlib.Path) -> None:
    path = tmp_path / "does_not_exist.json"

    assert assistant_thread_pointer.read_latest(path) is None


def test_read_latest_malformed_json_returns_none(tmp_path: pathlib.Path) -> None:
    path = tmp_path / "last_assistant_thread.json"
    path.write_text("not json {", encoding="utf-8")

    assert assistant_thread_pointer.read_latest(path) is None


def test_read_latest_missing_fields_returns_none(tmp_path: pathlib.Path) -> None:
    path = tmp_path / "last_assistant_thread.json"
    path.write_text('{"channel": "C123"}', encoding="utf-8")

    # A structurally valid JSON object that lacks thread_ts is still unusable.
    assert assistant_thread_pointer.read_latest(path) is None


def test_write_latest_creates_parent_directory(tmp_path: pathlib.Path) -> None:
    path = tmp_path / "nested" / "dir" / "last_assistant_thread.json"

    assistant_thread_pointer.write_latest("C123", "1.1", path=path)

    assert assistant_thread_pointer.read_latest(path) == ("C123", "1.1")

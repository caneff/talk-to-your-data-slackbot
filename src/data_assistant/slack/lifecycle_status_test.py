"""Tests for the injectable Slack lifecycle-status reporter.

These tests exercise ``lifecycle_status`` with a FAKE Slack client (recording
``conversations_open``/``chat_postMessage``/``chat_update`` calls) and a temp
state file, so no real Slack connection or signal is needed.
"""

from __future__ import annotations

import json
import pathlib
import typing

import data_assistant.slack.lifecycle_status as lifecycle_status


class FakeSlackClient:
    """Record the Slack WebClient calls the reporter makes.

    ``conversations_open`` returns a fixed channel id; ``chat_postMessage`` and
    ``chat_update`` record their kwargs and return a synthetic ``ts``.
    """

    def __init__(self, *, channel: str = "D123", ts: str = "1700000000.0001") -> None:
        self._channel = channel
        self._ts = ts
        self.opened_users: list[str] = []
        self.posted: list[dict[str, object]] = []
        self.updated: list[dict[str, object]] = []

    def conversations_open(self, *, users: str) -> dict[str, object]:
        self.opened_users.append(users)
        return {"channel": {"id": self._channel}}

    def chat_postMessage(self, **kwargs: object) -> dict[str, object]:
        self.posted.append(kwargs)
        return {"ts": self._ts, "channel": kwargs.get("channel")}

    def chat_update(self, **kwargs: object) -> dict[str, object]:
        self.updated.append(kwargs)
        return {"ts": kwargs.get("ts"), "channel": kwargs.get("channel")}


def test_compose_status_text_returns_exact_online_and_offline_strings() -> None:
    """The lifecycle strings are exact, emoji-prefixed status lines."""
    assert lifecycle_status.compose_status_text(online=True) == (
        "🟢 Data Assistant online"
    )
    assert lifecycle_status.compose_status_text(online=False) == (
        "🔴 Data Assistant offline"
    )


def test_post_online_opens_im_posts_text_and_persists_state(
    tmp_path: pathlib.Path,
) -> None:
    """``post_online`` opens the operator IM, posts online text, saves state."""
    client = FakeSlackClient(channel="D999", ts="1700000001.0002")
    state_path = tmp_path / "status_message.json"

    lifecycle_status.post_online(
        client=client,
        user_id="U-OPERATOR",
        state_path=state_path,
    )

    assert client.opened_users == ["U-OPERATOR"]
    assert len(client.posted) == 1
    posted = client.posted[0]
    assert posted["channel"] == "D999"
    assert posted["text"] == "🟢 Data Assistant online"
    saved = json.loads(state_path.read_text(encoding="utf-8"))
    assert saved == {"channel": "D999", "ts": "1700000001.0002"}


def test_mark_offline_updates_persisted_message_with_offline_text(
    tmp_path: pathlib.Path,
) -> None:
    """``mark_offline`` reads state and ``chat_update``s that channel+ts."""
    client = FakeSlackClient()
    state_path = tmp_path / "status_message.json"
    state_path.write_text(
        json.dumps({"channel": "D555", "ts": "1700000002.0003"}),
        encoding="utf-8",
    )

    lifecycle_status.mark_offline(client=client, state_path=state_path)

    assert client.posted == []
    assert len(client.updated) == 1
    updated = client.updated[0]
    assert updated["channel"] == "D555"
    assert updated["ts"] == "1700000002.0003"
    assert updated["text"] == "🔴 Data Assistant offline"


def test_mark_offline_with_missing_state_best_effort_posts_without_raising(
    tmp_path: pathlib.Path,
) -> None:
    """A missing state file falls back to a best-effort offline post."""
    client = FakeSlackClient()
    state_path = tmp_path / "does_not_exist.json"

    # Must not raise even though there is no persisted message to update.
    lifecycle_status.mark_offline(
        client=client,
        state_path=state_path,
        user_id="U-OPERATOR",
    )

    assert client.updated == []
    assert len(client.posted) == 1
    posted = client.posted[0]
    assert posted["text"] == "🔴 Data Assistant offline"


def test_mark_offline_swallows_client_errors(tmp_path: pathlib.Path) -> None:
    """Shutdown status posting is best-effort and never raises."""
    state_path = tmp_path / "status_message.json"
    state_path.write_text(
        json.dumps({"channel": "D555", "ts": "1700000002.0003"}),
        encoding="utf-8",
    )

    class ExplodingClient:
        def chat_update(self, **kwargs: object) -> dict[str, object]:
            del kwargs
            raise RuntimeError("slack is down")

        def chat_postMessage(self, **kwargs: object) -> dict[str, object]:
            del kwargs
            raise RuntimeError("slack is down")

    client = typing.cast(lifecycle_status.SlackStatusClient, ExplodingClient())

    # No exception escapes even though every Slack call fails.
    lifecycle_status.mark_offline(client=client, state_path=state_path)

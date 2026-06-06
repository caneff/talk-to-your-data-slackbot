"""Self-reported running-state lifecycle status posted to the operator's DM.

The Data Assistant cannot show a presence dot or a profile status: a Socket Mode
bot user has no connection-tracked presence (the manifest ``always_online`` flag
is binary and static) and bots have no editable profile (``users.profile.set``
needs a *user* token). The only self-report available with a bot token is posting
a *message* via ``chat:write``. So this module posts ``🟢 Data Assistant online``
on startup and ``chat.update``s the SAME message to ``🔴 Data Assistant offline``
on graceful shutdown.

This module is deliberately PURE and INJECTABLE: it imports no ``os.environ``,
no ``signal``, and no Bolt symbols. Callers pass the Slack ``WebClient``
(``App.client``) and a state-file path. That keeps it unit-testable with a fake
client and a temp file (see ``lifecycle_status_test.py``).

State (``{"channel", "ts"}``) is persisted to a small JSON file so the shutdown
edit can target the same message. If that state is missing or unreadable at
shutdown, ``mark_offline`` falls back to a best-effort fresh offline post.

Accepted limitation: a non-graceful kill (``kill -9`` / OOM) cannot run any
shutdown code, so it leaves a stale ``🟢 Data Assistant online`` message until the
next start. Ctrl-C is ``SIGINT`` and IS graceful, so it is covered.
"""

from __future__ import annotations

import json
import logging
import pathlib
import typing

logger = logging.getLogger(__name__)

_ONLINE_TEXT = "🟢 Data Assistant online"
_OFFLINE_TEXT = "🔴 Data Assistant offline"


class SlackStatusClient(typing.Protocol):
    """Minimal Slack ``WebClient`` surface the reporter relies on.

    Matches the Bolt ``App.client`` shape (``conversations_open`` /
    ``chat_postMessage`` / ``chat_update``); tests pass a fake exposing these.
    """

    def conversations_open(self, *, users: str) -> typing.Any:  # noqa: ANN401
        """Open (or fetch) the IM channel with the given user id."""

    def chat_postMessage(self, **kwargs: typing.Any) -> typing.Any:  # noqa: ANN401
        """Post a message; returns a response carrying ``ts``."""

    def chat_update(self, **kwargs: typing.Any) -> typing.Any:  # noqa: ANN401
        """Edit an existing message identified by ``channel`` + ``ts``."""


def compose_status_text(*, online: bool) -> str:
    """Return the exact lifecycle status line for the given running state."""
    return _ONLINE_TEXT if online else _OFFLINE_TEXT


def post_online(
    *,
    client: SlackStatusClient,
    user_id: str,
    state_path: pathlib.Path,
) -> None:
    """Open the operator IM, post the online status, and persist its location.

    Opens the IM with ``conversations_open(users=user_id)``, posts
    ``🟢 Data Assistant online`` to the returned channel, and writes
    ``{"channel", "ts"}`` to ``state_path`` so shutdown can edit the same message.
    """
    open_response = client.conversations_open(users=user_id)
    channel = _channel_id_from_open_response(open_response)
    post_response = client.chat_postMessage(
        channel=channel,
        text=compose_status_text(online=True),
    )
    ts = _ts_from_response(post_response)
    _write_state(state_path, channel=channel, ts=ts)


def mark_offline(
    *,
    client: SlackStatusClient,
    state_path: pathlib.Path,
    user_id: str | None = None,
) -> None:
    """Edit the persisted online message to offline; never raise.

    Reads ``{"channel", "ts"}`` from ``state_path`` and ``chat_update``s that
    message to ``🔴 Data Assistant offline``. If the state is missing/unreadable
    and ``user_id`` is given, falls back to a best-effort fresh offline post.
    All Slack/IO errors are swallowed and logged: shutdown status posting is
    best-effort and must never block a graceful exit.
    """
    try:
        state = _read_state(state_path)
    except (OSError, ValueError) as error:
        logger.warning("Could not read lifecycle status state: %s", error)
        state = None

    offline_text = compose_status_text(online=False)
    try:
        if state is not None:
            client.chat_update(
                channel=state["channel"],
                ts=state["ts"],
                text=offline_text,
            )
            return
        _post_fresh_offline(client=client, user_id=user_id, text=offline_text)
    except Exception as error:  # noqa: BLE001 -- best-effort shutdown report.
        logger.warning("Could not post offline lifecycle status: %s", error)


def _post_fresh_offline(
    *,
    client: SlackStatusClient,
    user_id: str | None,
    text: str,
) -> None:
    if user_id is None:
        logger.warning(
            "No lifecycle status state and no operator id; skipping offline post."
        )
        return
    open_response = client.conversations_open(users=user_id)
    channel = _channel_id_from_open_response(open_response)
    client.chat_postMessage(channel=channel, text=text)


def _channel_id_from_open_response(response: typing.Any) -> str:  # noqa: ANN401
    channel = response["channel"]
    if isinstance(channel, dict):
        return typing.cast(str, channel["id"])
    return typing.cast(str, channel)


def _ts_from_response(response: typing.Any) -> str:  # noqa: ANN401
    return typing.cast(str, response["ts"])


def _write_state(state_path: pathlib.Path, *, channel: str, ts: str) -> None:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(
        json.dumps({"channel": channel, "ts": ts}),
        encoding="utf-8",
    )


def _read_state(state_path: pathlib.Path) -> dict[str, str] | None:
    if not state_path.exists():
        return None
    data = json.loads(state_path.read_text(encoding="utf-8"))
    channel = data.get("channel")
    ts = data.get("ts")
    if not isinstance(channel, str) or not isinstance(ts, str):
        raise ValueError("lifecycle status state is missing channel/ts")
    return {"channel": channel, "ts": ts}

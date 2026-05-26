"""Tests for the local Slack Runtime Adapter startup boundary.

These tests intentionally exercise only the local startup contract for issue
#23. They do not import Slack Bolt directly, create real Slack clients, open a
Socket Mode connection, or adapt incoming Slack events. The next issue owns live
`message.im` handling; this file only proves that local configuration and
startup wiring are safe before that event path exists.
"""

from __future__ import annotations

import dataclasses
import typing

import pytest

import data_assistant.slack_runtime as slack_runtime


def test_load_slack_runtime_config_reads_required_env_vars() -> None:
    """Load only the two Slack tokens required for local Socket Mode startup."""
    config = slack_runtime.load_slack_runtime_config(
        {
            "SLACK_BOT_TOKEN": "xoxb-test-token",
            "SLACK_APP_TOKEN": "xapp-test-token",
        }
    )

    assert config == slack_runtime.SlackRuntimeConfig(
        bot_token="xoxb-test-token",
        app_token="xapp-test-token",
    )


def test_load_slack_runtime_config_names_all_missing_env_vars() -> None:
    """Fail locally with useful names while avoiding secret values in errors."""
    with pytest.raises(slack_runtime.SlackRuntimeConfigError) as error_info:
        slack_runtime.load_slack_runtime_config({})

    # The exact missing names matter because this message is the developer's
    # first clue during local startup. Token values must never appear here.
    assert (
        str(error_info.value)
        == "Missing required Slack environment variables: "
        "SLACK_BOT_TOKEN, SLACK_APP_TOKEN"
    )


def test_run_socket_mode_from_env_fails_before_constructing_runtime_objects() -> None:
    """Validate config before constructing Slack Bolt runtime objects."""
    app_factory_calls: list[str] = []
    handler_factory_calls: list[str] = []

    # These factories record calls instead of constructing Slack Bolt objects.
    # If validation happens in the wrong order, the assertions below catch it.
    def app_factory(*, token: str) -> object:
        app_factory_calls.append(token)
        return object()

    def socket_mode_handler_factory(
        *, app_token: str, app: object
    ) -> FakeSocketModeHandler:
        handler_factory_calls.append(app_token)
        return FakeSocketModeHandler(app_token=app_token, app=app)

    with pytest.raises(slack_runtime.SlackRuntimeConfigError):
        slack_runtime.run_socket_mode_from_env(
            {},
            app_factory=app_factory,
            socket_mode_handler_factory=socket_mode_handler_factory,
        )

    # Missing config must stop startup before any Slack-facing object exists.
    assert app_factory_calls == []
    assert handler_factory_calls == []


@dataclasses.dataclass
class FakeSocketModeHandler:
    """Small stand-in for Slack Bolt's Socket Mode handler.

    The production handler blocks while listening to Slack. This fake keeps the
    same observable startup surface for the test: it stores the app token and
    app object it was built with, and records whether startup was requested.
    """

    app_token: str
    app: object
    starts: int = 0

    def start(self) -> None:
        """Record that startup was requested without opening a Slack socket."""
        self.starts += 1


def test_run_socket_mode_from_env_builds_and_starts_socket_mode_runtime() -> None:
    """Wire valid env config into injected app and Socket Mode factories."""
    app_tokens: list[str] = []
    created_handlers: list[FakeSocketModeHandler] = []

    # The fake app is deliberately plain data. That keeps the assertion focused
    # on token flow and avoids depending on Slack Bolt internals.
    def app_factory(*, token: str) -> object:
        app_tokens.append(token)
        return {"bot_token": token}

    def socket_mode_handler_factory(
        *, app_token: str, app: object
    ) -> FakeSocketModeHandler:
        handler = FakeSocketModeHandler(app_token=app_token, app=app)
        created_handlers.append(handler)
        return handler

    # The cast keeps the test strict-type friendly while the runtime function
    # exposes the narrower protocol used by production code.
    handler = typing.cast(
        FakeSocketModeHandler,
        slack_runtime.run_socket_mode_from_env(
            {
                "SLACK_BOT_TOKEN": "xoxb-live-token",
                "SLACK_APP_TOKEN": "xapp-live-token",
            },
            app_factory=app_factory,
            socket_mode_handler_factory=socket_mode_handler_factory,
        ),
    )

    # These assertions prove the local startup path is wired end-to-end without
    # contacting Slack: bot token into the app, app token into the handler, then
    # exactly one startup request.
    assert app_tokens == ["xoxb-live-token"]
    assert len(created_handlers) == 1
    assert handler is created_handlers[0]
    assert handler.app == {"bot_token": "xoxb-live-token"}
    assert handler.app_token == "xapp-live-token"
    assert handler.starts == 1

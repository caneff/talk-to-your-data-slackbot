from __future__ import annotations

import dataclasses
import typing

import pytest

import data_assistant.slack_runtime as slack_runtime


def test_load_slack_runtime_config_reads_required_env_vars() -> None:
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
    with pytest.raises(slack_runtime.SlackRuntimeConfigError) as error_info:
        slack_runtime.load_slack_runtime_config({})

    assert (
        str(error_info.value)
        == "Missing required Slack environment variables: "
        "SLACK_BOT_TOKEN, SLACK_APP_TOKEN"
    )


def test_run_socket_mode_from_env_fails_before_constructing_runtime_objects() -> None:
    app_factory_calls: list[str] = []
    handler_factory_calls: list[str] = []

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

    assert app_factory_calls == []
    assert handler_factory_calls == []


@dataclasses.dataclass
class FakeSocketModeHandler:
    app_token: str
    app: object
    starts: int = 0

    def start(self) -> None:
        self.starts += 1


def test_run_socket_mode_from_env_builds_and_starts_socket_mode_runtime() -> None:
    app_tokens: list[str] = []
    created_handlers: list[FakeSocketModeHandler] = []

    def app_factory(*, token: str) -> object:
        app_tokens.append(token)
        return {"bot_token": token}

    def socket_mode_handler_factory(
        *, app_token: str, app: object
    ) -> FakeSocketModeHandler:
        handler = FakeSocketModeHandler(app_token=app_token, app=app)
        created_handlers.append(handler)
        return handler

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

    assert app_tokens == ["xoxb-live-token"]
    assert len(created_handlers) == 1
    assert handler is created_handlers[0]
    assert handler.app == {"bot_token": "xoxb-live-token"}
    assert handler.app_token == "xapp-live-token"
    assert handler.starts == 1

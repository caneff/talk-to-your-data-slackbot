"""Slack Runtime Adapter startup for local Socket Mode execution."""

from __future__ import annotations

import collections.abc as collections_abc
import dataclasses
import os
import sys
import typing

if typing.TYPE_CHECKING:
    from slack_bolt import App as SlackBoltApp


@dataclasses.dataclass(frozen=True)
class SlackRuntimeConfig:
    """Required environment-backed config for local Slack runtime startup."""

    bot_token: str
    app_token: str


class SlackRuntimeConfigError(ValueError):
    """Raised when required Slack runtime configuration is missing."""


class SocketModeHandler(typing.Protocol):
    """Minimal Socket Mode handler shape used by local startup."""

    def start(self) -> None:
        """Start the Socket Mode event loop."""


AppFactory: typing.TypeAlias = collections_abc.Callable[..., object]
SocketModeHandlerFactory: typing.TypeAlias = collections_abc.Callable[
    ..., SocketModeHandler
]


def load_slack_runtime_config(
    environ: collections_abc.Mapping[str, str] = os.environ,
) -> SlackRuntimeConfig:
    """Load required Slack runtime config from environment variables only."""
    missing_names = [
        name
        for name in ("SLACK_BOT_TOKEN", "SLACK_APP_TOKEN")
        if not environ.get(name)
    ]
    if missing_names:
        joined_names = ", ".join(missing_names)
        raise SlackRuntimeConfigError(
            f"Missing required Slack environment variables: {joined_names}"
        )
    return SlackRuntimeConfig(
        bot_token=environ["SLACK_BOT_TOKEN"],
        app_token=environ["SLACK_APP_TOKEN"],
    )


def _default_app_factory(*, token: str) -> object:
    from slack_bolt import App

    return App(token=token)


def _default_socket_mode_handler_factory(
    *, app_token: str, app: object
) -> SocketModeHandler:
    from slack_bolt.adapter.socket_mode import SocketModeHandler as BoltHandler

    return typing.cast(
        SocketModeHandler,
        BoltHandler(
            app=typing.cast("SlackBoltApp", app),
            app_token=app_token,
        ),
    )


def run_socket_mode_from_env(
    environ: collections_abc.Mapping[str, str] = os.environ,
    *,
    app_factory: AppFactory = _default_app_factory,
    socket_mode_handler_factory: SocketModeHandlerFactory = (
        _default_socket_mode_handler_factory
    ),
) -> SocketModeHandler:
    """Build and start the local Slack Runtime Adapter from environment config."""
    config = load_slack_runtime_config(environ)
    app = app_factory(token=config.bot_token)
    handler = socket_mode_handler_factory(app_token=config.app_token, app=app)
    handler.start()
    return handler


def main() -> int:
    """Run the local Socket Mode entrypoint."""
    try:
        run_socket_mode_from_env()
    except SlackRuntimeConfigError as error:
        print(str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

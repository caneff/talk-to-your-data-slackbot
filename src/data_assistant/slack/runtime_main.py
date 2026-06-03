"""Slack Runtime Adapter startup for local Socket Mode execution."""

from __future__ import annotations

import argparse
import collections.abc as collections_abc
import dataclasses
import logging
import os
import pathlib
import sys
import typing

import dotenv

import data_assistant.question_interpreter as question_interpreter
import data_assistant.semantic_layer.loader as semantic_layer_loader
import data_assistant.slack as slack_assistant
import data_assistant.slack.cli_common as cli_common
import data_assistant.slack.composition as composition

if typing.TYPE_CHECKING:
    from slack_bolt import App as SlackBoltApp

logger = logging.getLogger(__name__)


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


def _load_env_file(
    path: str | pathlib.Path = ".env",
) -> None:
    """Load local dotenv values without overriding exported environment vars."""
    dotenv.load_dotenv(dotenv_path=path, override=False)


def load_slack_runtime_config(
    environ: collections_abc.Mapping[str, str] = os.environ,
) -> SlackRuntimeConfig:
    """Load required Slack runtime config from environment variables only."""
    missing_names = [
        name for name in ("SLACK_BOT_TOKEN", "SLACK_APP_TOKEN") if not environ.get(name)
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
    connection_factory: composition.ConnectionFactory | None = None,
    internal_identity_resolver: slack_assistant.AssistantIdentityResolver = (
        slack_assistant.default_identity
    ),
    answer_path: slack_assistant.AnswerPath | None = None,
    interaction_log_path: pathlib.Path | None = None,
) -> SocketModeHandler:
    """Build and start the local Slack Runtime Adapter from environment config."""
    config = load_slack_runtime_config(environ)
    # Build the adapter (and validate OpenAI config) before constructing the
    # Slack Bolt app, so a misconfigured run fails before any runtime objects
    # exist. The adapter needs no app, so only handler registration waits on it.
    adapter: slack_assistant.AssistantAdapter | None = None
    if connection_factory is not None:
        active_answer_path = answer_path or composition.build_openai_answer_path(
            environ
        )
        adapter = composition.build_adapter(
            connection_factory=connection_factory,
            answer_path=active_answer_path,
            internal_identity_resolver=internal_identity_resolver,
            environ=environ,
            interaction_log_path=interaction_log_path,
        )
    app = app_factory(token=config.bot_token)
    if adapter is not None:
        slack_assistant.register_assistant_handlers(app=app, adapter=adapter)
    handler = socket_mode_handler_factory(app_token=config.app_token, app=app)
    handler.start()
    return handler


def main(
    argv: collections_abc.Sequence[str] = (),
    *,
    env_file: str | pathlib.Path = ".env",
) -> int:
    """Run the local Socket Mode entrypoint."""
    try:
        args = _parse_args(argv)
        active_env_file = args.env_file or env_file
        _load_env_file(active_env_file)
        connection_factory = cli_common.connection_factory_from_args(args)
        answer_path = _configured_answer_path(os.environ, args)
        run_socket_mode_from_env(
            connection_factory=connection_factory,
            internal_identity_resolver=slack_assistant.dev_identity,
            answer_path=answer_path,
            interaction_log_path=args.interaction_log_path,
        )
    except (
        OSError,
        ValueError,
        SlackRuntimeConfigError,
        question_interpreter.OpenAIQuestionInterpreterConfigError,
    ) as error:
        print(str(error), file=sys.stderr)
        return 1
    return 0


def _parse_args(argv: collections_abc.Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the local Slack adapter.")
    cli_common.add_data_source_args(parser)
    parser.add_argument(
        "--interaction-log-path",
        type=pathlib.Path,
        default=None,
        help=(
            "Interaction Log JSONL path. Defaults to "
            f"{composition.INTERACTION_LOG_PATH_ENV_VAR} or logs/interactions.jsonl."
        ),
    )
    args = parser.parse_args(argv)
    cli_common.enforce_seed_requires_duckdb(parser, args)
    return args


def _configured_answer_path(
    environ: collections_abc.Mapping[str, str],
    args: argparse.Namespace,
) -> slack_assistant.AnswerPath | None:
    # No flag: load the retail app-run layer (retail is the single dataset; the
    # data-source args default --semantic-layer-path to the retail layer).
    semantic_layer = semantic_layer_loader.load_semantic_layer(args.semantic_layer_path)
    return composition.build_openai_answer_path(environ, semantic_layer=semantic_layer)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

"""Slack Runtime Adapter startup for local Socket Mode execution."""

from __future__ import annotations

import argparse
import collections.abc as collections_abc
import contextlib
import dataclasses
import logging
import os
import pathlib
import sys
import typing

import dotenv
import duckdb

import data_assistant.local_duckdb_fixture as local_duckdb_fixture
import data_assistant.question_interpreter as question_interpreter
import data_assistant.reasoning_layer as reasoning_layer
import data_assistant.semantic_layer.loader as semantic_layer_loader
import data_assistant.semantic_layer.schema as schema
import data_assistant.slack_assistant as slack_assistant
import data_assistant.workflow.contracts as contracts
import data_assistant.workflow.runner as workflow_runner

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
ConnectionFactory: typing.TypeAlias = slack_assistant.ConnectionFactory


def build_openai_answer_path(
    environ: collections_abc.Mapping[str, str],
    *,
    semantic_layer: schema.SemanticLayer | None = None,
) -> slack_assistant.AnswerPath:
    """Build the Slack answer path using the live OpenAI Question Interpreter."""
    provider = question_interpreter.build_openai_question_interpreter_provider(environ)
    reasoning_provider = reasoning_layer.build_openai_reasoning_provider(environ)

    def answer_path(
        connection: duckdb.DuckDBPyConnection,
        question: str,
        internal_identity: contracts.InternalIdentity,
    ) -> slack_assistant.SlackWorkflowResult:
        return workflow_runner.run_data_assistant(
            connection,
            question,
            question_interpreter_provider=provider,
            reasoning_provider=reasoning_provider,
            internal_identity=internal_identity,
            semantic_layer=semantic_layer,
        )

    return answer_path


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


def _dev_connection_factory() -> contextlib.AbstractContextManager[
    duckdb.DuckDBPyConnection
]:
    """Provide a tiny local DuckDB fixture for manual Slack smoke testing."""
    return local_duckdb_fixture.connect_orders(
        (
            ("2026-01-03", "North", "1200.00"),
            ("2026-01-10", "South", "800.00"),
            ("2026-01-17", "North", "300.00"),
        )
    )


def build_duckdb_connection_factory(
    duckdb_path: str | pathlib.Path,
    *,
    seed_sql_path: str | pathlib.Path | None = None,
) -> ConnectionFactory:
    """Build a runtime connection factory for a configured DuckDB database."""
    duckdb_location = str(duckdb_path)
    seed_sql = (
        pathlib.Path(seed_sql_path).read_text(encoding="utf-8")
        if seed_sql_path is not None
        else None
    )

    @contextlib.contextmanager
    def connect() -> collections_abc.Generator[duckdb.DuckDBPyConnection]:
        connection = duckdb.connect(duckdb_location)
        try:
            if seed_sql is not None:
                connection.execute(seed_sql)
            yield connection
        finally:
            connection.close()

    return connect


def run_socket_mode_from_env(
    environ: collections_abc.Mapping[str, str] = os.environ,
    *,
    app_factory: AppFactory = _default_app_factory,
    socket_mode_handler_factory: SocketModeHandlerFactory = (
        _default_socket_mode_handler_factory
    ),
    connection_factory: ConnectionFactory | None = None,
    internal_identity_resolver: slack_assistant.AssistantIdentityResolver = (
        slack_assistant.default_identity
    ),
    answer_path: slack_assistant.AnswerPath | None = None,
) -> SocketModeHandler:
    """Build and start the local Slack Runtime Adapter from environment config."""
    config = load_slack_runtime_config(environ)
    active_answer_path = answer_path
    if connection_factory is not None and active_answer_path is None:
        active_answer_path = build_openai_answer_path(environ)
    app = app_factory(token=config.bot_token)
    if connection_factory is not None:
        if active_answer_path is None:
            raise AssertionError("answer path should be configured")
        adapter = slack_assistant.AssistantAdapter(
            connection_factory=connection_factory,
            answer_path=active_answer_path,
            internal_identity_resolver=internal_identity_resolver,
        )
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
        connection_factory = _configured_connection_factory(args)
        answer_path = _configured_answer_path(os.environ, args)
        run_socket_mode_from_env(
            connection_factory=connection_factory,
            internal_identity_resolver=slack_assistant.dev_identity,
            answer_path=answer_path,
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
    parser.add_argument(
        "--env-file",
        type=pathlib.Path,
        default=None,
        help="dotenv file to load before startup. Defaults to .env.",
    )
    parser.add_argument(
        "--semantic-layer-path",
        type=pathlib.Path,
        default=None,
        help="Semantic Layer directory to load instead of semantic_layer/.",
    )
    parser.add_argument(
        "--duckdb-path",
        type=str,
        default=None,
        help="DuckDB database location to use instead of the tiny dev fixture.",
    )
    parser.add_argument(
        "--seed-sql-path",
        type=pathlib.Path,
        default=None,
        help="Optional SQL file to run whenever the DuckDB connection opens.",
    )
    args = parser.parse_args(argv)
    if args.seed_sql_path is not None and args.duckdb_path is None:
        parser.error("--seed-sql-path requires --duckdb-path")
    return args


def _configured_connection_factory(args: argparse.Namespace) -> ConnectionFactory:
    if args.duckdb_path is None:
        return _dev_connection_factory
    return build_duckdb_connection_factory(
        args.duckdb_path,
        seed_sql_path=args.seed_sql_path,
    )


def _configured_answer_path(
    environ: collections_abc.Mapping[str, str],
    args: argparse.Namespace,
) -> slack_assistant.AnswerPath | None:
    if args.semantic_layer_path is None:
        return None
    semantic_layer = semantic_layer_loader.load_semantic_layer(args.semantic_layer_path)
    return build_openai_answer_path(environ, semantic_layer=semantic_layer)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

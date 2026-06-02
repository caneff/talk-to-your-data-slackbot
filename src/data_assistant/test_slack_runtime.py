"""Tests for the local Slack Runtime Adapter startup wiring.

The Slack edge behavior (greeting, status, pipeline, fallback) lives in
``slack_assistant`` and is tested in ``test_slack_assistant``. These tests cover
runtime startup: config loading, the OpenAI answer path, the DuckDB connection
factory, Assistant-handler registration before startup, and the ``main`` CLI.
"""

from __future__ import annotations

import collections.abc
import contextlib
import pathlib
import typing

import duckdb
import pytest

import data_assistant.openai_support as openai_support
import data_assistant.semantic_layer.schema as schema
import data_assistant.slack_assistant as slack_assistant
import data_assistant.slack_runtime as slack_runtime
import data_assistant.workflow.contracts as contracts

VALID_SLACK_ENV = {
    "SLACK_BOT_TOKEN": "xoxb-live-token",
    "SLACK_APP_TOKEN": "xapp-live-token",
}


def _connection_factory_should_not_run() -> contextlib.AbstractContextManager[
    duckdb.DuckDBPyConnection
]:
    raise AssertionError("startup validation should fail before opening data")


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
        str(error_info.value) == "Missing required Slack environment variables: "
        "SLACK_BOT_TOKEN, SLACK_APP_TOKEN"
    )


def test_build_openai_answer_path_uses_openai_provider_without_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_providers: list[object] = []
    captured_reasoning_providers: list[object] = []

    class FakeProvider:
        pass

    class FakeReasoningProvider:
        pass

    def fake_build_openai_provider(
        environ: collections.abc.Mapping[str, str],
        *,
        client: object | None = None,
    ) -> FakeProvider:
        del client
        assert environ["OPENAI_API_KEY"] == "test-key"
        return FakeProvider()

    def fake_build_openai_reasoning_provider(
        environ: collections.abc.Mapping[str, str],
        *,
        client: object | None = None,
    ) -> FakeReasoningProvider:
        del client
        assert environ["OPENAI_API_KEY"] == "test-key"
        return FakeReasoningProvider()

    def fake_run_data_assistant(
        connection: duckdb.DuckDBPyConnection,
        question: str,
        internal_identity: contracts.InternalIdentity,
        progress_sink: contracts.ProgressSink,
        semantic_layer: object | None = None,
        question_interpreter_provider: object | None = None,
        reasoning_provider: object | None = None,
    ) -> contracts.FinalResponse:
        del connection, question, internal_identity, progress_sink, semantic_layer
        captured_providers.append(question_interpreter_provider)
        captured_reasoning_providers.append(reasoning_provider)
        return contracts.FinalResponse(
            text="openai answer path",
            trust_summary=contracts.TrustSummary(),
            response_kind=contracts.ResponseKind.ANSWER,
        )

    monkeypatch.setattr(
        slack_runtime.question_interpreter,
        "build_openai_question_interpreter_provider",
        fake_build_openai_provider,
    )
    monkeypatch.setattr(
        slack_runtime.reasoning_layer,
        "build_openai_reasoning_provider",
        fake_build_openai_reasoning_provider,
    )
    monkeypatch.setattr(
        slack_runtime.workflow_runner,
        "run_data_assistant",
        fake_run_data_assistant,
    )
    answer_path = slack_runtime.build_openai_answer_path(
        VALID_SLACK_ENV | {"OPENAI_API_KEY": "test-key"}
    )

    with duckdb.connect(":memory:") as connection:
        result = answer_path(
            connection,
            "What was total revenue by region in January 2026?",
            contracts.InternalIdentity(identity_id="slack_user:U123"),
            lambda status: None,
        )

    assert isinstance(result, contracts.FinalResponse)
    assert result.response_kind == contracts.ResponseKind.ANSWER
    assert len(captured_providers) == 1
    assert isinstance(captured_providers[0], FakeProvider)
    assert len(captured_reasoning_providers) == 1
    assert isinstance(captured_reasoning_providers[0], FakeReasoningProvider)


@pytest.mark.parametrize(
    ("environ", "connection_factory", "expected_error"),
    [
        pytest.param(
            {},
            None,
            slack_runtime.SlackRuntimeConfigError,
            id="missing Slack config",
        ),
        pytest.param(
            VALID_SLACK_ENV,
            _connection_factory_should_not_run,
            slack_runtime.question_interpreter.OpenAIQuestionInterpreterConfigError,
            id="missing OpenAI config",
        ),
    ],
)
def test_run_socket_mode_from_env_fails_before_constructing_runtime_objects(
    environ: collections.abc.Mapping[str, str],
    connection_factory: slack_runtime.ConnectionFactory | None,
    expected_error: type[Exception],
) -> None:
    """Validate config before constructing Slack Bolt runtime objects."""
    runtime_factories = RecordingRuntimeFactories()

    with pytest.raises(expected_error):
        slack_runtime.run_socket_mode_from_env(
            environ,
            app_factory=runtime_factories.app_factory,
            socket_mode_handler_factory=runtime_factories.socket_mode_handler_factory,
            connection_factory=connection_factory,
        )

    assert runtime_factories.app_tokens == []
    assert runtime_factories.created_handlers == []


class FakeSocketModeHandler:
    """Small stand-in for Slack Bolt's Socket Mode handler.

    The production handler blocks while listening to Slack. This fake keeps the
    same observable startup surface for the test: it stores the app token and
    app object it was built with, and records whether startup was requested.
    """

    def __init__(self, *, app_token: str, app: object) -> None:
        self.app_token = app_token
        self.app = app
        self.starts = 0

    def start(self) -> None:
        """Record that startup was requested without opening a Slack socket."""
        self.starts += 1


class RecordingRuntimeFactories:
    """Capture app and Socket Mode handler construction during startup tests."""

    def __init__(self, *, app: object | None = None) -> None:
        self.app = app
        self.app_tokens: list[str] = []
        self.created_handlers: list[FakeSocketModeHandler] = []

    def app_factory(self, *, token: str) -> object:
        self.app_tokens.append(token)
        if self.app is not None:
            return self.app
        return {"bot_token": token}

    def socket_mode_handler_factory(
        self, *, app_token: str, app: object
    ) -> FakeSocketModeHandler:
        handler = FakeSocketModeHandler(app_token=app_token, app=app)
        self.created_handlers.append(handler)
        return handler


def sentinel_answer_path(
    connection: duckdb.DuckDBPyConnection,
    question: str,
    internal_identity: contracts.InternalIdentity,
    progress_sink: contracts.ProgressSink,
) -> contracts.FinalResponse:
    del connection, question, internal_identity, progress_sink
    return contracts.FinalResponse(
        text="answer",
        trust_summary=contracts.TrustSummary(),
        response_kind=contracts.ResponseKind.ANSWER,
    )


def test_run_socket_mode_from_env_registers_assistant_before_startup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Startup builds the Assistant adapter and mounts it before listening."""
    app = object()
    runtime_factories = RecordingRuntimeFactories(app=app)
    registered: list[tuple[object, slack_assistant.AssistantAdapter]] = []

    def fake_register_assistant_handlers(
        *,
        app: object,
        adapter: slack_assistant.AssistantAdapter,
    ) -> None:
        registered.append((app, adapter))

    monkeypatch.setattr(
        slack_assistant,
        "register_assistant_handlers",
        fake_register_assistant_handlers,
    )

    def connection_factory() -> contextlib.AbstractContextManager[
        duckdb.DuckDBPyConnection
    ]:
        raise AssertionError("startup should register handlers without opening data")

    handler = typing.cast(
        FakeSocketModeHandler,
        slack_runtime.run_socket_mode_from_env(
            VALID_SLACK_ENV,
            app_factory=runtime_factories.app_factory,
            socket_mode_handler_factory=runtime_factories.socket_mode_handler_factory,
            connection_factory=connection_factory,
            answer_path=sentinel_answer_path,
        ),
    )

    assert runtime_factories.app_tokens == ["xoxb-live-token"]
    assert len(registered) == 1
    registered_app, registered_adapter = registered[0]
    assert registered_app is app
    assert registered_adapter.connection_factory is connection_factory
    assert registered_adapter.answer_path is sentinel_answer_path
    # The default OpenAI model label is sourced from the environ onto the
    # adapter so the Interaction Log records a real model (ADR-0016).
    assert registered_adapter.model_label == openai_support.DEFAULT_OPENAI_MODEL
    assert registered_adapter.log_path == slack_runtime.interaction_log.DEFAULT_LOG_PATH
    assert len(runtime_factories.created_handlers) == 1
    assert handler is runtime_factories.created_handlers[0]
    assert handler.app is app
    assert handler.app_token == "xapp-live-token"
    assert handler.starts == 1


def test_run_socket_mode_from_env_threads_openai_model_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An OPENAI_MODEL override flows onto the adapter's model_label."""
    app = object()
    runtime_factories = RecordingRuntimeFactories(app=app)
    registered: list[slack_assistant.AssistantAdapter] = []

    def fake_register_assistant_handlers(
        *,
        app: object,
        adapter: slack_assistant.AssistantAdapter,
    ) -> None:
        del app
        registered.append(adapter)

    monkeypatch.setattr(
        slack_assistant,
        "register_assistant_handlers",
        fake_register_assistant_handlers,
    )

    def connection_factory() -> contextlib.AbstractContextManager[
        duckdb.DuckDBPyConnection
    ]:
        raise AssertionError("startup should register handlers without opening data")

    slack_runtime.run_socket_mode_from_env(
        VALID_SLACK_ENV | {"OPENAI_MODEL": "gpt-test-override"},
        app_factory=runtime_factories.app_factory,
        socket_mode_handler_factory=runtime_factories.socket_mode_handler_factory,
        connection_factory=connection_factory,
        answer_path=sentinel_answer_path,
    )

    assert registered[0].model_label == "gpt-test-override"


def test_run_socket_mode_from_env_threads_interaction_log_path_env(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: pathlib.Path,
) -> None:
    """Render can point the Interaction Log at its persistent disk."""
    app = object()
    runtime_factories = RecordingRuntimeFactories(app=app)
    registered: list[slack_assistant.AssistantAdapter] = []
    log_path = tmp_path / "render" / "interactions.jsonl"

    def fake_register_assistant_handlers(
        *,
        app: object,
        adapter: slack_assistant.AssistantAdapter,
    ) -> None:
        del app
        registered.append(adapter)

    monkeypatch.setattr(
        slack_assistant,
        "register_assistant_handlers",
        fake_register_assistant_handlers,
    )

    def connection_factory() -> contextlib.AbstractContextManager[
        duckdb.DuckDBPyConnection
    ]:
        raise AssertionError("startup should register handlers without opening data")

    slack_runtime.run_socket_mode_from_env(
        VALID_SLACK_ENV | {slack_runtime.INTERACTION_LOG_PATH_ENV_VAR: str(log_path)},
        app_factory=runtime_factories.app_factory,
        socket_mode_handler_factory=runtime_factories.socket_mode_handler_factory,
        connection_factory=connection_factory,
        answer_path=sentinel_answer_path,
    )

    assert registered[0].log_path == log_path


def test_build_duckdb_connection_factory_runs_seed_sql(tmp_path: pathlib.Path) -> None:
    seed_sql_path = tmp_path / "seed.sql"
    seed_sql_path.write_text(
        "create table demo_value (value integer); insert into demo_value values (42);",
        encoding="utf-8",
    )
    connection_factory = slack_runtime.build_duckdb_connection_factory(
        ":memory:",
        seed_sql_path=seed_sql_path,
    )

    with connection_factory() as connection:
        row = connection.execute("select value from demo_value").fetchone()

    assert row == (42,)


def test_main_uses_configured_semantic_layer_and_duckdb_paths(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: pathlib.Path,
) -> None:
    semantic_layer_path = tmp_path / "semantic-layer"
    seed_sql_path = tmp_path / "seed.sql"
    seed_sql_path.write_text(
        "create table demo_value (value integer); insert into demo_value values (7);",
        encoding="utf-8",
    )
    loaded_semantic_layer = typing.cast(schema.SemanticLayer, object())
    loaded_paths: list[pathlib.Path] = []
    built_answer_paths: list[slack_assistant.AnswerPath] = []
    received_connection_factories: list[slack_runtime.ConnectionFactory | None] = []

    def fake_load_semantic_layer(path: pathlib.Path) -> schema.SemanticLayer:
        loaded_paths.append(path)
        return loaded_semantic_layer

    def fake_build_openai_answer_path(
        environ: collections.abc.Mapping[str, str],
        *,
        semantic_layer: schema.SemanticLayer | None = None,
    ) -> slack_assistant.AnswerPath:
        del environ
        assert semantic_layer is loaded_semantic_layer
        built_answer_paths.append(sentinel_answer_path)
        return sentinel_answer_path

    def fake_run_socket_mode_from_env(
        environ: collections.abc.Mapping[str, str] = {},
        *,
        app_factory: slack_runtime.AppFactory | None = None,
        socket_mode_handler_factory: (
            slack_runtime.SocketModeHandlerFactory | None
        ) = None,
        connection_factory: slack_runtime.ConnectionFactory | None = None,
        internal_identity_resolver: (
            slack_assistant.AssistantIdentityResolver | None
        ) = None,
        answer_path: slack_assistant.AnswerPath | None = None,
        interaction_log_path: pathlib.Path | None = None,
    ) -> FakeSocketModeHandler:
        del environ, app_factory, socket_mode_handler_factory
        del internal_identity_resolver, interaction_log_path
        assert answer_path is sentinel_answer_path
        assert connection_factory is not None
        received_connection_factories.append(connection_factory)
        with connection_factory() as connection:
            row = connection.execute("select value from demo_value").fetchone()
        assert row == (7,)
        return FakeSocketModeHandler(app_token="xapp-test-token", app=object())

    monkeypatch.setattr(
        slack_runtime.semantic_layer_loader,
        "load_semantic_layer",
        fake_load_semantic_layer,
    )
    monkeypatch.setattr(
        slack_runtime,
        "build_openai_answer_path",
        fake_build_openai_answer_path,
    )
    monkeypatch.setattr(
        slack_runtime,
        "run_socket_mode_from_env",
        fake_run_socket_mode_from_env,
    )

    exit_code = slack_runtime.main(
        [
            "--semantic-layer-path",
            str(semantic_layer_path),
            "--duckdb-path",
            ":memory:",
            "--seed-sql-path",
            str(seed_sql_path),
        ],
        env_file=tmp_path / ".env",
    )

    assert exit_code == 0
    assert loaded_paths == [semantic_layer_path]
    assert built_answer_paths == [sentinel_answer_path]
    assert len(received_connection_factories) == 1


def test_main_starts_socket_mode_with_dev_connection_factory(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: pathlib.Path,
) -> None:
    dev_connection_factory = slack_runtime.dev_connection_factory
    dev_identity_resolver: slack_assistant.AssistantIdentityResolver = (
        slack_assistant.dev_identity
    )
    received_connection_factory: list[slack_runtime.ConnectionFactory | None] = []
    received_identity_resolver: list[
        slack_assistant.AssistantIdentityResolver | None
    ] = []

    def fake_run_socket_mode_from_env(
        environ: collections.abc.Mapping[str, str] = {},
        *,
        app_factory: slack_runtime.AppFactory | None = None,
        socket_mode_handler_factory: (
            slack_runtime.SocketModeHandlerFactory | None
        ) = None,
        connection_factory: slack_runtime.ConnectionFactory | None = None,
        internal_identity_resolver: (
            slack_assistant.AssistantIdentityResolver | None
        ) = None,
        answer_path: slack_assistant.AnswerPath | None = None,
        interaction_log_path: pathlib.Path | None = None,
    ) -> FakeSocketModeHandler:
        del environ, app_factory, socket_mode_handler_factory, answer_path
        del interaction_log_path
        received_connection_factory.append(connection_factory)
        received_identity_resolver.append(internal_identity_resolver)
        return FakeSocketModeHandler(app_token="xapp-test-token", app=object())

    monkeypatch.setattr(
        slack_runtime,
        "run_socket_mode_from_env",
        fake_run_socket_mode_from_env,
    )

    exit_code = slack_runtime.main(env_file=tmp_path / ".env")

    assert exit_code == 0
    assert received_connection_factory == [dev_connection_factory]
    assert received_identity_resolver == [dev_identity_resolver]


def test_main_threads_explicit_interaction_log_path(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: pathlib.Path,
) -> None:
    received_log_paths: list[pathlib.Path | None] = []
    log_path = tmp_path / "custom-interactions.jsonl"

    def fake_run_socket_mode_from_env(
        environ: collections.abc.Mapping[str, str] = {},
        *,
        app_factory: slack_runtime.AppFactory | None = None,
        socket_mode_handler_factory: (
            slack_runtime.SocketModeHandlerFactory | None
        ) = None,
        connection_factory: slack_runtime.ConnectionFactory | None = None,
        internal_identity_resolver: (
            slack_assistant.AssistantIdentityResolver | None
        ) = None,
        answer_path: slack_assistant.AnswerPath | None = None,
        interaction_log_path: pathlib.Path | None = None,
    ) -> FakeSocketModeHandler:
        del environ, app_factory, socket_mode_handler_factory
        del connection_factory, internal_identity_resolver, answer_path
        received_log_paths.append(interaction_log_path)
        return FakeSocketModeHandler(app_token="xapp-test-token", app=object())

    monkeypatch.setattr(
        slack_runtime,
        "run_socket_mode_from_env",
        fake_run_socket_mode_from_env,
    )

    exit_code = slack_runtime.main(
        ["--interaction-log-path", str(log_path)],
        env_file=tmp_path / ".env",
    )

    assert exit_code == 0
    assert received_log_paths == [log_path]

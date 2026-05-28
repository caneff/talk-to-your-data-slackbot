"""Tests for the local Slack Runtime Adapter startup and DM event adapter."""

from __future__ import annotations

import collections.abc
import contextlib
import dataclasses
import inspect
import os
import pathlib
import typing

import duckdb
import pytest

import data_assistant.llm_question_interpreter as llm_question_interpreter
import data_assistant.slack_boundary as slack_boundary
import data_assistant.slack_runtime as slack_runtime
import data_assistant.testing_support as testing_support
import data_assistant.workflow.contracts as contracts
import data_assistant.workflow.runner as workflow_runner


def create_empty_chat_post_calls() -> list[dict[str, str]]:
    return []


def create_empty_registered_handlers() -> dict[
    str, collections.abc.Callable[..., object]
]:
    return {}


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


def test_build_openai_answer_path_uses_openai_provider_without_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_providers: list[object] = []

    class FakeProvider:
        pass

    def fake_build_openai_provider(
        environ: collections.abc.Mapping[str, str],
        *,
        client_factory: object | None = None,
    ) -> FakeProvider:
        del client_factory
        assert environ["OPENAI_API_KEY"] == "test-key"
        return FakeProvider()

    def fake_run_data_assistant(
        connection: duckdb.DuckDBPyConnection,
        question: str,
        internal_identity: contracts.InternalIdentity,
        semantic_layer: object | None = None,
        question_interpreter_provider: object | None = None,
    ) -> contracts.FinalResponse:
        del connection, question, internal_identity, semantic_layer
        captured_providers.append(question_interpreter_provider)
        return contracts.FinalResponse(
            text="openai answer path",
            trust_summary=contracts.TrustSummary(),
            response_kind="answer",
        )

    monkeypatch.setattr(
        slack_runtime.llm_question_interpreter,
        "build_openai_question_interpreter_provider",
        fake_build_openai_provider,
    )
    monkeypatch.setattr(
        slack_runtime.workflow_runner,
        "run_data_assistant",
        fake_run_data_assistant,
    )
    answer_path = slack_runtime.build_openai_answer_path(
        {
            "SLACK_BOT_TOKEN": "xoxb-test-token",
            "SLACK_APP_TOKEN": "xapp-test-token",
            "OPENAI_API_KEY": "test-key",
        }
    )

    with duckdb.connect(":memory:") as connection:
        result = answer_path(
            connection,
            "What was total revenue by region in January 2026?",
            contracts.InternalIdentity(identity_id="slack_user:U123"),
        )

    assert isinstance(result, contracts.FinalResponse)
    assert result.response_kind == "answer"
    assert len(captured_providers) == 1
    assert isinstance(captured_providers[0], FakeProvider)


def test_load_env_file_uses_dotenv_without_overriding_existing_env(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: pathlib.Path,
) -> None:
    """Load local dotenv values while preserving explicit shell exports."""
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            (
                "SLACK_BOT_TOKEN=xoxb-dotenv-token",
                "SLACK_APP_TOKEN=xapp-dotenv-token",
            )
        )
    )
    monkeypatch.delenv("SLACK_BOT_TOKEN", raising=False)
    monkeypatch.setenv("SLACK_APP_TOKEN", "xapp-exported-token")

    slack_runtime._load_env_file(env_file)  # pyright: ignore[reportPrivateUsage]

    assert os.environ["SLACK_BOT_TOKEN"] == "xoxb-dotenv-token"
    assert os.environ["SLACK_APP_TOKEN"] == "xapp-exported-token"


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


def test_run_socket_mode_from_env_requires_openai_config_before_runtime_objects(
) -> None:
    """Validate live interpreter config before constructing Slack runtime objects."""
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

    def connection_factory(
    ) -> contextlib.AbstractContextManager[duckdb.DuckDBPyConnection]:
        raise AssertionError("missing OpenAI config should fail before startup")

    with pytest.raises(
        slack_runtime.llm_question_interpreter.OpenAIQuestionInterpreterConfigError
    ):
        slack_runtime.run_socket_mode_from_env(
            {
                "SLACK_BOT_TOKEN": "xoxb-live-token",
                "SLACK_APP_TOKEN": "xapp-live-token",
            },
            app_factory=app_factory,
            socket_mode_handler_factory=socket_mode_handler_factory,
            connection_factory=connection_factory,
        )

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


@dataclasses.dataclass
class RecordingSlackClient:
    """Capture Slack DM replies without calling Slack APIs."""

    calls: list[dict[str, str]] = dataclasses.field(
        default_factory=create_empty_chat_post_calls
    )

    def chat_postMessage(self, *, channel: str, thread_ts: str, text: str) -> None:
        self.calls.append(
            {
                "channel": channel,
                "thread_ts": thread_ts,
                "text": text,
            }
        )


@dataclasses.dataclass
class RecordingBoltApp:
    """Capture registered Bolt event handlers without importing Slack Bolt."""

    registered_handlers: dict[str, collections.abc.Callable[..., object]] = (
        dataclasses.field(default_factory=create_empty_registered_handlers)
    )

    def event(
        self, event_name: str
    ) -> collections.abc.Callable[
        [collections.abc.Callable[..., object]],
        collections.abc.Callable[..., object],
    ]:
        def register(
            handler: collections.abc.Callable[..., object],
        ) -> collections.abc.Callable[..., object]:
            self.registered_handlers[event_name] = handler
            return handler

        return register


def sentinel_answer_path(
    connection: duckdb.DuckDBPyConnection,
    question: str,
    internal_identity: contracts.InternalIdentity,
) -> contracts.FinalResponse:
    del connection, question, internal_identity
    return contracts.FinalResponse(
        text="answer",
        trust_summary=contracts.TrustSummary(),
        response_kind="answer",
    )


def test_handle_socket_mode_event_routes_human_dm_through_existing_boundary(
    canonical_question: str,
    connect_orders: testing_support.OrdersConnector,
) -> None:
    ack_calls: list[str] = []
    calls: list[str] = []
    client = RecordingSlackClient()
    seen_questions: list[str] = []
    seen_identity_ids: list[str] = []
    event: slack_runtime.SlackBoltMessageEvent = {
        "type": "message",
        "channel": "D123",
        "channel_type": "im",
        "user": "U123",
        "text": canonical_question,
        "ts": "1710000000.654321",
    }
    final_response = contracts.FinalResponse(
        text="Final answer text.",
        trust_summary=contracts.TrustSummary(datasets=("Commerce Revenue",)),
        response_kind="answer",
    )

    def acknowledge() -> None:
        ack_calls.append("ack")
        calls.append("ack")

    def connection_factory(
    ) -> contextlib.AbstractContextManager[duckdb.DuckDBPyConnection]:
        calls.append("connection_factory")
        return connect_orders((("2026-01-03", "North", "1200.00"),))

    def answer_path(
        _connection: object,
        question: str,
        internal_identity: contracts.InternalIdentity,
    ) -> slack_boundary.SlackWorkflowResult:
        calls.append("answer_path")
        seen_questions.append(question)
        seen_identity_ids.append(internal_identity.identity_id)
        return final_response

    result = slack_runtime.handle_socket_mode_event(
        event=event,
        ack=acknowledge,
        client=client,
        connection_factory=connection_factory,
        answer_path=answer_path,
    )

    assert result is not None
    assert ack_calls == ["ack"]
    assert calls == ["ack", "connection_factory", "answer_path"]
    assert seen_questions == [canonical_question]
    assert seen_identity_ids == ["slack_user:U123"]
    assert client.calls == [
        {
            "channel": "D123",
            "thread_ts": "1710000000.654321",
            "text": "Final answer text.",
        }
    ]


@pytest.mark.parametrize(
    ("event", "label"),
    [
        (
            typing.cast(
                slack_runtime.SlackBoltMessageEvent,
                {
                    "type": "message",
                    "channel": "D123",
                    "channel_type": "im",
                    "user": "U123",
                    "text": "hello",
                    "ts": "1710000000.111111",
                    "bot_id": "B123",
                },
            ),
            "bot message",
        ),
        (
            typing.cast(
                slack_runtime.SlackBoltMessageEvent,
                {
                    "type": "message",
                    "channel": "C123",
                    "channel_type": "channel",
                    "user": "U123",
                    "text": "hello",
                    "ts": "1710000000.222222",
                },
            ),
            "non-DM message",
        ),
        (
            typing.cast(
                slack_runtime.SlackBoltMessageEvent,
                {
                    "type": "app_mention",
                    "channel": "C123",
                    "channel_type": "channel",
                    "user": "U123",
                    "text": "hello",
                    "ts": "1710000000.333333",
                },
            ),
            "unsupported event type",
        ),
    ],
    ids=lambda value: value if isinstance(value, str) else None,
)
def test_handle_socket_mode_event_acknowledges_and_ignores_unsupported_events(
    event: slack_runtime.SlackBoltMessageEvent,
    label: str,
) -> None:
    del label
    ack_calls: list[str] = []
    client = RecordingSlackClient()
    connection_factory_calls: list[str] = []
    answer_path_calls: list[str] = []

    def acknowledge() -> None:
        ack_calls.append("ack")

    def connection_factory(
    ) -> contextlib.AbstractContextManager[duckdb.DuckDBPyConnection]:
        connection_factory_calls.append("connection_factory")
        raise AssertionError("ignored events must not open a data connection")

    def answer_path(
        _connection: object,
        _question: str,
        _internal_identity: contracts.InternalIdentity,
    ) -> slack_boundary.SlackWorkflowResult:
        answer_path_calls.append("answer_path")
        raise AssertionError("ignored events must not run the answer path")

    result = slack_runtime.handle_socket_mode_event(
        event=event,
        ack=acknowledge,
        client=client,
        connection_factory=connection_factory,
        answer_path=answer_path,
    )

    assert result is None
    assert ack_calls == ["ack"]
    assert connection_factory_calls == []
    assert answer_path_calls == []
    assert client.calls == []


def test_run_socket_mode_from_env_registers_message_handler_before_startup() -> None:
    app = RecordingBoltApp()
    created_handlers: list[FakeSocketModeHandler] = []

    def app_factory(*, token: str) -> object:
        assert token == "xoxb-live-token"
        return app

    def socket_mode_handler_factory(
        *, app_token: str, app: object
    ) -> FakeSocketModeHandler:
        assert app is not None
        handler = FakeSocketModeHandler(app_token=app_token, app=app)
        created_handlers.append(handler)
        return handler

    def connection_factory(
    ) -> contextlib.AbstractContextManager[duckdb.DuckDBPyConnection]:
        raise AssertionError("startup should register handlers without opening data")

    slack_runtime.run_socket_mode_from_env(
        {
            "SLACK_BOT_TOKEN": "xoxb-live-token",
            "SLACK_APP_TOKEN": "xapp-live-token",
        },
        app_factory=app_factory,
        socket_mode_handler_factory=socket_mode_handler_factory,
        connection_factory=connection_factory,
        answer_path=sentinel_answer_path,
    )

    assert "message" in app.registered_handlers
    assert len(created_handlers) == 1
    assert created_handlers[0].starts == 1


def test_registered_message_handler_exposes_bolt_injected_arguments() -> None:
    app = RecordingBoltApp()

    def connection_factory(
    ) -> contextlib.AbstractContextManager[duckdb.DuckDBPyConnection]:
        raise AssertionError("argument inspection must not open data")

    slack_runtime.register_socket_mode_handlers(
        app=app,
        connection_factory=connection_factory,
        answer_path=sentinel_answer_path,
    )

    handler = app.registered_handlers["message"]

    assert inspect.getfullargspec(handler).args == ["event", "ack", "client"]


def test_main_starts_socket_mode_with_dev_connection_factory(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: pathlib.Path,
) -> None:
    dev_connection_factory = slack_runtime._dev_connection_factory  # pyright: ignore[reportPrivateUsage]
    dev_internal_identity_resolver = typing.cast(
        slack_boundary.InternalIdentityResolver,
        slack_runtime._dev_internal_identity_resolver,  # pyright: ignore[reportPrivateUsage]
    )
    received_connection_factory: list[slack_runtime.ConnectionFactory | None] = []
    received_identity_resolver: list[
        slack_boundary.InternalIdentityResolver | None
    ] = []
    received_answer_paths: list[slack_boundary.AnswerPath | None] = []

    def fake_run_socket_mode_from_env(
        environ: collections.abc.Mapping[str, str] = {},
        *,
        app_factory: slack_runtime.AppFactory | None = None,
        socket_mode_handler_factory: (
            slack_runtime.SocketModeHandlerFactory | None
        ) = None,
        connection_factory: slack_runtime.ConnectionFactory | None = None,
        internal_identity_resolver: (
            slack_boundary.InternalIdentityResolver | None
        ) = None,
        answer_path: slack_boundary.AnswerPath | None = None,
    ) -> FakeSocketModeHandler:
        del environ, app_factory, socket_mode_handler_factory
        received_connection_factory.append(connection_factory)
        received_identity_resolver.append(internal_identity_resolver)
        received_answer_paths.append(answer_path)
        return FakeSocketModeHandler(app_token="xapp-test-token", app=object())

    monkeypatch.setattr(
        slack_runtime,
        "run_socket_mode_from_env",
        fake_run_socket_mode_from_env,
    )

    exit_code = slack_runtime.main(env_file=tmp_path / ".env")

    assert exit_code == 0
    assert received_connection_factory == [dev_connection_factory]
    assert received_identity_resolver == [dev_internal_identity_resolver]
    assert received_answer_paths == [None]


def test_run_socket_mode_from_env_registers_dev_runtime_that_answers_canonical_dm(
    canonical_question: str,
    canonical_question_provider: llm_question_interpreter.QuestionInterpreterProvider,
) -> None:
    dev_connection_factory = slack_runtime._dev_connection_factory  # pyright: ignore[reportPrivateUsage]
    dev_internal_identity_resolver = typing.cast(
        slack_boundary.InternalIdentityResolver,
        slack_runtime._dev_internal_identity_resolver,  # pyright: ignore[reportPrivateUsage]
    )
    app = RecordingBoltApp()

    def app_factory(*, token: str) -> object:
        assert token == "xoxb-live-token"
        return app

    def socket_mode_handler_factory(
        *, app_token: str, app: object
    ) -> FakeSocketModeHandler:
        assert app_token == "xapp-live-token"
        assert app is not None
        return FakeSocketModeHandler(app_token=app_token, app=app)

    def answer_path(
        connection: duckdb.DuckDBPyConnection,
        question: str,
        internal_identity: contracts.InternalIdentity,
    ) -> slack_boundary.SlackWorkflowResult:
        return workflow_runner.run_data_assistant(
            connection,
            question,
            question_interpreter_provider=canonical_question_provider,
            internal_identity=internal_identity,
        )

    slack_runtime.run_socket_mode_from_env(
        {
            "SLACK_BOT_TOKEN": "xoxb-live-token",
            "SLACK_APP_TOKEN": "xapp-live-token",
        },
        app_factory=app_factory,
        socket_mode_handler_factory=socket_mode_handler_factory,
        connection_factory=dev_connection_factory,
        internal_identity_resolver=dev_internal_identity_resolver,
        answer_path=answer_path,
    )

    handler = app.registered_handlers["message"]
    ack_calls: list[str] = []
    client = RecordingSlackClient()
    event: slack_runtime.SlackBoltMessageEvent = {
        "type": "message",
        "channel": "D123",
        "channel_type": "im",
        "user": "U999",
        "text": canonical_question,
        "ts": "1710000000.654321",
    }

    result = typing.cast(
        slack_boundary.SlackRequestResult,
        handler(
            event=event,
            ack=lambda: ack_calls.append("ack"),
            client=client,
        ),
    )

    assert result.acknowledged is True
    assert ack_calls == ["ack"]
    assert len(client.calls) == 1
    assert client.calls[0]["thread_ts"] == "1710000000.654321"
    assert "Trust Summary:" in client.calls[0]["text"]
    assert "North" in client.calls[0]["text"]
    assert "South" in client.calls[0]["text"]
    assert "I cannot answer safely" not in client.calls[0]["text"]

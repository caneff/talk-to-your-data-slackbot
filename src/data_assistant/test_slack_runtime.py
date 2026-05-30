"""Tests for the local Slack Runtime Adapter startup and DM event adapter."""

from __future__ import annotations

import collections.abc
import contextlib
import pathlib
import typing

import duckdb
import pytest

import data_assistant.local_orders_fixture as local_orders_fixture
import data_assistant.slack_boundary as slack_boundary
import data_assistant.slack_runtime as slack_runtime
import data_assistant.workflow.contracts as contracts

VALID_SLACK_ENV = {
    "SLACK_BOT_TOKEN": "xoxb-live-token",
    "SLACK_APP_TOKEN": "xapp-live-token",
}


def bolt_message_event(
    *,
    event_type: str = "message",
    channel: str = "D123",
    channel_type: str = "im",
    user: str = "U123",
    text: str = "hello",
    ts: str = "1710000000.000000",
    bot_id: str | None = None,
    subtype: str | None = None,
) -> slack_runtime.SlackBoltMessageEvent:
    event: slack_runtime.SlackBoltMessageEvent = {
        "type": event_type,
        "channel": channel,
        "channel_type": channel_type,
        "user": user,
        "text": text,
        "ts": ts,
    }
    if bot_id is not None:
        event["bot_id"] = bot_id
    if subtype is not None:
        event["subtype"] = subtype
    return event


def _connection_factory_should_not_run(
) -> contextlib.AbstractContextManager[duckdb.DuckDBPyConnection]:
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
        client: object | None = None,
    ) -> FakeProvider:
        del client
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
            response_kind=contracts.ResponseKind.ANSWER,
        )

    monkeypatch.setattr(
        slack_runtime.question_interpreter,
        "build_openai_question_interpreter_provider",
        fake_build_openai_provider,
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
        )

    assert isinstance(result, contracts.FinalResponse)
    assert result.response_kind == contracts.ResponseKind.ANSWER
    assert len(captured_providers) == 1
    assert isinstance(captured_providers[0], FakeProvider)


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


class RecordingSlackClient:
    """Capture Slack DM replies without calling Slack APIs."""

    def __init__(self) -> None:
        self.calls: list[dict[str, str]] = []

    def chat_postMessage(self, *, channel: str, thread_ts: str, text: str) -> None:
        self.calls.append(
            {
                "channel": channel,
                "thread_ts": thread_ts,
                "text": text,
            }
        )


class RecordingBoltApp:
    """Capture registered Bolt event handlers without importing Slack Bolt."""

    def __init__(self) -> None:
        self.registered_handlers: dict[
            str, collections.abc.Callable[..., object]
        ] = {}

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
        response_kind=contracts.ResponseKind.ANSWER,
    )


def test_handle_socket_mode_event_routes_human_dm_through_existing_boundary(
    canonical_question: str,
    connect_orders: local_orders_fixture.OrdersConnector,
) -> None:
    ack_calls: list[str] = []
    calls: list[str] = []
    client = RecordingSlackClient()
    seen_questions: list[str] = []
    seen_identity_ids: list[str] = []
    event = bolt_message_event(
        user="U123",
        text=canonical_question,
        ts="1710000000.654321",
    )
    final_response = contracts.FinalResponse(
        text="Final answer text.",
        trust_summary=contracts.TrustSummary(datasets=("Commerce Revenue",)),
        response_kind=contracts.ResponseKind.ANSWER,
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
    "event",
    [
        pytest.param(
            bolt_message_event(
                ts="1710000000.111111",
                bot_id="B123",
            ),
            id="bot message",
        ),
        pytest.param(
            bolt_message_event(
                channel="C123",
                channel_type="channel",
                ts="1710000000.222222",
            ),
            id="non-DM message",
        ),
        pytest.param(
            bolt_message_event(
                event_type="app_mention",
                channel="C123",
                channel_type="channel",
                ts="1710000000.333333",
            ),
            id="unsupported event type",
        ),
    ],
)
def test_handle_socket_mode_event_acknowledges_and_ignores_unsupported_events(
    event: slack_runtime.SlackBoltMessageEvent,
) -> None:
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
    runtime_factories = RecordingRuntimeFactories(app=app)

    def connection_factory(
    ) -> contextlib.AbstractContextManager[duckdb.DuckDBPyConnection]:
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
    assert "message" in app.registered_handlers
    assert len(runtime_factories.created_handlers) == 1
    assert handler is runtime_factories.created_handlers[0]
    assert handler.app is app
    assert handler.app_token == "xapp-live-token"
    assert handler.starts == 1


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
        del environ, app_factory, socket_mode_handler_factory, answer_path
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
    assert received_identity_resolver == [dev_internal_identity_resolver]

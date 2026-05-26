"""Slack Runtime Adapter startup for local Socket Mode execution."""

from __future__ import annotations

import collections.abc as collections_abc
import contextlib
import dataclasses
import os
import sys
import typing

import duckdb

import data_assistant.access_controller as access_controller
import data_assistant.slack_boundary as slack_boundary
import data_assistant.testing_support as testing_support
import data_assistant.workflow.contracts as contracts
import data_assistant.workflow.runner as workflow_runner

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


class SlackBoltAppEventRegistrar(typing.Protocol):
    """Minimal Slack Bolt app surface used by runtime registration."""

    def event(
        self, event_name: str
    ) -> collections_abc.Callable[[collections_abc.Callable[..., object]], object]:
        """Register a handler for one Slack event type."""
        ...


AppFactory: typing.TypeAlias = collections_abc.Callable[..., object]
SocketModeHandlerFactory: typing.TypeAlias = collections_abc.Callable[
    ..., SocketModeHandler
]
Ack: typing.TypeAlias = collections_abc.Callable[[], None]
ConnectionFactory: typing.TypeAlias = collections_abc.Callable[
    [], contextlib.AbstractContextManager[duckdb.DuckDBPyConnection]
]


class SlackBoltMessageEvent(typing.TypedDict):
    """Slack Bolt event fields used by the DM runtime adapter."""

    type: str
    channel: str
    channel_type: str
    user: str
    text: str
    ts: str
    bot_id: typing.NotRequired[str]
    subtype: typing.NotRequired[str]


class SlackBoltChatClient(typing.Protocol):
    """Minimal Slack client surface used by the runtime adapter."""

    def chat_postMessage(self, *, channel: str, thread_ts: str, text: str) -> None:
        """Post a threaded DM response back to Slack."""


class _SocketModeSlackGateway:
    """Bridge boundary deliveries to the Slack Bolt ack/client shape."""

    def __init__(self, *, ack: Ack, client: SlackBoltChatClient) -> None:
        self._ack = ack
        self._client = client
        self._acknowledged = False

    def acknowledge(self) -> None:
        if not self._acknowledged:
            self._ack()
            self._acknowledged = True

    def deliver_response(self, delivery: slack_boundary.SlackDelivery) -> None:
        self._client.chat_postMessage(
            channel=delivery.channel,
            thread_ts=delivery.thread_ts,
            text=delivery.text,
        )


def _default_answer_path(
    connection: duckdb.DuckDBPyConnection,
    question: str,
    internal_identity: contracts.InternalIdentity,
) -> slack_boundary.SlackWorkflowResult:
    """Use the standard Data Assistant workflow for Slack DM requests."""
    return workflow_runner.run_data_assistant(
        connection,
        question,
        internal_identity=internal_identity,
    )


def _default_internal_identity_resolver(
    event: slack_boundary.SlackInnerEvent,
) -> contracts.InternalIdentity:
    """Map Slack DM user identity into the workflow contract."""
    return contracts.InternalIdentity(identity_id=f"slack_user:{event['user']}")


def _dev_internal_identity_resolver(
    event: slack_boundary.SlackInnerEvent,
) -> contracts.InternalIdentity:
    """Use the local allowed identity for manual development smoke testing."""
    del event
    return access_controller.DEFAULT_LOCAL_ALLOWED_IDENTITY


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


def handle_socket_mode_event(
    *,
    event: SlackBoltMessageEvent,
    ack: Ack,
    client: SlackBoltChatClient,
    connection_factory: ConnectionFactory,
    answer_path: slack_boundary.AnswerPath = _default_answer_path,
    internal_identity_resolver: slack_boundary.InternalIdentityResolver = (
        _default_internal_identity_resolver
    ),
) -> slack_boundary.SlackRequestResult | None:
    """Route one human DM event through the existing Slack boundary."""
    gateway = _SocketModeSlackGateway(ack=ack, client=client)
    if not _is_supported_human_dm(event):
        gateway.acknowledge()
        return None

    gateway.acknowledge()
    payload: slack_boundary.SlackEventPayload = {
        "event_id": "",
        "event": {
            "type": event["type"],
            "channel": event["channel"],
            "user": event["user"],
            "text": event["text"],
            "ts": event["ts"],
        },
    }
    with connection_factory() as connection:
        return slack_boundary.handle_slack_event(
            payload=payload,
            connection=connection,
            gateway=gateway,
            answer_path=answer_path,
            internal_identity_resolver=internal_identity_resolver,
        )


def _is_supported_human_dm(event: SlackBoltMessageEvent) -> bool:
    """Filter Slack events down to human direct messages only."""
    return (
        event.get("type") == "message"
        and event.get("channel_type") == "im"
        and bool(event.get("user"))
        and not event.get("bot_id")
        and not event.get("subtype")
    )


def register_socket_mode_handlers(
    *,
    app: SlackBoltAppEventRegistrar,
    connection_factory: ConnectionFactory,
    answer_path: slack_boundary.AnswerPath = _default_answer_path,
    internal_identity_resolver: slack_boundary.InternalIdentityResolver = (
        _default_internal_identity_resolver
    ),
) -> None:
    """Register Slack Bolt event handlers that adapt DMs into the boundary."""

    def handle_message_event(
        *,
        event: SlackBoltMessageEvent,
        ack: Ack,
        client: SlackBoltChatClient,
    ) -> slack_boundary.SlackRequestResult | None:
        return handle_socket_mode_event(
            event=event,
            ack=ack,
            client=client,
            connection_factory=connection_factory,
            answer_path=answer_path,
            internal_identity_resolver=internal_identity_resolver,
        )

    app.event("message")(handle_message_event)


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


def _dev_connection_factory(
) -> contextlib.AbstractContextManager[duckdb.DuckDBPyConnection]:
    """Provide a tiny local DuckDB fixture for manual Slack smoke testing."""
    return testing_support.connect_orders(
        (
            ("2026-01-03", "North", "1200.00"),
            ("2026-01-10", "South", "800.00"),
            ("2026-01-17", "North", "300.00"),
        )
    )


def run_socket_mode_from_env(
    environ: collections_abc.Mapping[str, str] = os.environ,
    *,
    app_factory: AppFactory = _default_app_factory,
    socket_mode_handler_factory: SocketModeHandlerFactory = (
        _default_socket_mode_handler_factory
    ),
    connection_factory: ConnectionFactory | None = None,
    internal_identity_resolver: slack_boundary.InternalIdentityResolver = (
        _default_internal_identity_resolver
    ),
) -> SocketModeHandler:
    """Build and start the local Slack Runtime Adapter from environment config."""
    config = load_slack_runtime_config(environ)
    app = app_factory(token=config.bot_token)
    if connection_factory is not None:
        register_socket_mode_handlers(
            app=typing.cast(SlackBoltAppEventRegistrar, app),
            connection_factory=connection_factory,
            internal_identity_resolver=internal_identity_resolver,
        )
    handler = socket_mode_handler_factory(app_token=config.app_token, app=app)
    handler.start()
    return handler


def main() -> int:
    """Run the local Socket Mode entrypoint."""
    try:
        run_socket_mode_from_env(
            connection_factory=_dev_connection_factory,
            internal_identity_resolver=_dev_internal_identity_resolver,
        )
    except SlackRuntimeConfigError as error:
        print(str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

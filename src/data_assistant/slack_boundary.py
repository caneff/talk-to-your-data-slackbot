"""Slack-facing request envelope for the Data Assistant."""

from __future__ import annotations

import collections.abc as collections_abc
import dataclasses
import typing

import duckdb

import data_assistant.workflow.contracts as contracts
import data_assistant.workflow.runner as workflow_runner


class SlackInnerEvent(typing.TypedDict):
    type: str
    channel: str
    user: str
    text: str
    ts: str


class SlackEventPayload(typing.TypedDict):
    event_id: str
    event: SlackInnerEvent


@dataclasses.dataclass(frozen=True)
class SlackDelivery:
    channel: str
    thread_ts: str
    text: str


@dataclasses.dataclass(frozen=True)
class SlackRequestResult:
    acknowledged: bool
    delivery: SlackDelivery


class SlackGateway(typing.Protocol):
    def acknowledge(self) -> None:
        """Record an HTTP-style Slack acknowledgement."""

    def deliver_response(self, delivery: SlackDelivery) -> None:
        """Deliver a threaded Slack response."""


AnswerPath: typing.TypeAlias = collections_abc.Callable[
    [duckdb.DuckDBPyConnection, str],
    contracts.WorkflowResult,
]


def handle_slack_event(
    payload: SlackEventPayload,
    connection: duckdb.DuckDBPyConnection,
    gateway: SlackGateway,
    answer_path: AnswerPath = workflow_runner.run_data_assistant,
) -> SlackRequestResult:
    """Acknowledge a Slack message event and deliver the workflow response."""
    gateway.acknowledge()
    result = answer_path(connection, payload["event"]["text"])
    delivery = SlackDelivery(
        channel=payload["event"]["channel"],
        thread_ts=payload["event"]["ts"],
        text=_render_workflow_result(result),
    )
    gateway.deliver_response(delivery)
    return SlackRequestResult(acknowledged=True, delivery=delivery)


def _render_workflow_result(result: contracts.WorkflowResult) -> str:
    if isinstance(result, contracts.NonAnswer):
        return (
            f"{result.reason}\n\n"
            f"Unresolved ambiguities: {', '.join(result.unresolved_ambiguities)}\n"
            f"Next step: {result.next_step}"
        )
    return result.final_response.text

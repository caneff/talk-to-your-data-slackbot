"""Slack-facing request envelope for the Data Assistant.

This module is the thin boundary between a Slack-like message event and the
core Data Assistant workflow. It acknowledges the request, extracts one Data
Question from the event text, runs the supplied answer path, and delivers a
threaded Slack-style response through an injected gateway.
"""

from __future__ import annotations

import collections.abc as collections_abc
import dataclasses
import typing

import duckdb

import data_assistant.workflow.contracts as contracts
import data_assistant.workflow.runner as workflow_runner


class SlackInnerEvent(typing.TypedDict):
    """Slack-like message event fields consumed by the boundary.

    Notes
    -----
    The handler assumes a well-formed message event. Signature checks,
    retries, bot-message filtering, and malformed payload handling belong to a
    future runtime adapter.
    """

    type: str
    channel: str
    user: str
    text: str
    ts: str


class SlackEventPayload(typing.TypedDict):
    """Slack-like Events API wrapper for one message event."""

    event_id: str
    event: SlackInnerEvent


@dataclasses.dataclass(frozen=True)
class SlackDelivery:
    """Threaded response prepared for the Slack-facing gateway.

    Attributes
    ----------
    channel : str
        Slack channel that should receive the response.
    thread_ts : str
        Timestamp of the original Slack message. Real Slack delivery should use
        this as `thread_ts` so responses appear in the original thread.
    text : str
        User-facing Final Response or Non-Answer Response text.
    """

    channel: str
    thread_ts: str
    text: str


@dataclasses.dataclass(frozen=True)
class SlackRequestResult:
    """Result returned after one fake Slack event is handled.

    Attributes
    ----------
    acknowledged : bool
        Whether the HTTP-style Slack Acknowledgement was produced.
    delivery : SlackDelivery
        Slack-style response delivered through the injected gateway.
    """

    acknowledged: bool
    delivery: SlackDelivery


class SlackGateway(typing.Protocol):
    """Minimal Slack-facing output port used by the request boundary."""

    def acknowledge(self) -> None:
        """Record an HTTP-style Slack acknowledgement."""

    def deliver_response(self, delivery: SlackDelivery) -> None:
        """Deliver a threaded Slack response."""


SlackWorkflowResult: typing.TypeAlias = contracts.WorkflowResult | contracts.NonAnswer

AnswerPath: typing.TypeAlias = collections_abc.Callable[
    [duckdb.DuckDBPyConnection, str],
    SlackWorkflowResult,
]


def handle_slack_event(
    payload: SlackEventPayload,
    connection: duckdb.DuckDBPyConnection,
    gateway: SlackGateway,
    answer_path: AnswerPath = workflow_runner.run_data_assistant,
) -> SlackRequestResult:
    """Acknowledge a Slack message event and deliver the workflow response.

    Parameters
    ----------
    payload : SlackEventPayload
        Slack-like Events API payload containing one message event. The inner
        event text is treated as the Data Question.
    connection : duckdb.DuckDBPyConnection
        Ready-to-use data connection supplied by the outer runtime layer.
    gateway : SlackGateway
        Output port that records the acknowledgement and response delivery.
    answer_path : AnswerPath, optional
        Callable used to produce the core workflow result. Defaults to the real
        Data Assistant runner and can be replaced by tests to prove
        acknowledgement ordering. Test doubles may still return a `NonAnswer`
        directly even when the default workflow composes one into a
        Final Response.

    Returns
    -------
    SlackRequestResult
        The acknowledgement state and Slack-style delivery record.

    Notes
    -----
    The acknowledgement is sent before `answer_path` runs. Delivery uses the
    original Slack message timestamp as `thread_ts` so the response can become a
    real threaded reply when a Slack SDK adapter is added.
    """
    gateway.acknowledge()
    result = answer_path(connection, payload["event"]["text"])
    delivery = SlackDelivery(
        channel=payload["event"]["channel"],
        thread_ts=payload["event"]["ts"],
        text=_render_workflow_result(result),
    )
    gateway.deliver_response(delivery)
    return SlackRequestResult(acknowledged=True, delivery=delivery)


def _render_workflow_result(result: SlackWorkflowResult) -> str:
    """Render a core workflow result as user-facing Slack text."""
    if isinstance(result, contracts.NonAnswer):
        return (
            f"{result.reason}\n\n"
            f"Unresolved ambiguities: {', '.join(result.unresolved_ambiguities)}\n"
            f"Next step: {result.next_step}"
        )
    if isinstance(result, contracts.FinalResponse):
        return result.text
    return result.final_response.text

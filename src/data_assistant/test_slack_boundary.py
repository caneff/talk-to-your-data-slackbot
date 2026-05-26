from __future__ import annotations

import dataclasses

import duckdb

import data_assistant.slack_boundary as slack_boundary
import data_assistant.testing_support as testing_support
import data_assistant.workflow.contracts as contracts


def create_empty_deliveries() -> list[slack_boundary.SlackDelivery]:
    return []


def create_empty_calls() -> list[str]:
    return []


@dataclasses.dataclass
class RecordingSlackGateway:
    acknowledgements: int = 0
    calls: list[str] = dataclasses.field(default_factory=create_empty_calls)
    deliveries: list[slack_boundary.SlackDelivery] = dataclasses.field(
        default_factory=create_empty_deliveries
    )

    def acknowledge(self) -> None:
        self.calls.append("acknowledge")
        self.acknowledgements += 1

    def deliver_response(self, delivery: slack_boundary.SlackDelivery) -> None:
        self.calls.append("deliver_response")
        self.deliveries.append(delivery)


def test_handle_slack_event_delivers_final_response_in_original_thread(
    canonical_question: str,
    connect_orders: testing_support.OrdersConnector,
) -> None:
    gateway = RecordingSlackGateway()
    payload: slack_boundary.SlackEventPayload = {
        "event_id": "Ev123",
        "event": {
            "type": "message",
            "channel": "C123",
            "user": "U123",
            "text": canonical_question,
            "ts": "1710000000.123456",
        },
    }
    order_rows = (
        ("2026-01-03", "North", "1200.00"),
        ("2026-01-08", "South", "850.00"),
        ("2026-01-15", "West", "1600.00"),
        ("2026-01-20", " ", "250.00"),
        ("2026-01-22", "North", "300.00"),
        ("2026-01-28", "East", "950.00"),
        ("2026-01-29", "East", None),
        ("2026-02-01", None, None),
    )

    with connect_orders(order_rows) as connection:
        slack_boundary.handle_slack_event(
            payload=payload,
            connection=connection,
            gateway=gateway,
        )

    assert gateway.deliveries == [
        slack_boundary.SlackDelivery(
            channel="C123",
            thread_ts="1710000000.123456",
            text=(
                "Total revenue in January 2026 was $5,150.00, grouped across 5 "
                "regions.\n\n"
                "- West: $1,600.00\n"
                "- North: $1,500.00\n"
                "- East: $950.00\n"
                "- South: $850.00\n"
                "- Unknown: $250.00\n\n"
                "Trust Summary: Curated Dataset: Commerce Revenue. "
                "Dataset Table: orders. "
                "Time range: January 2026. "
                "Filters: none. "
                "Caveats: Commerce order data refreshed through 2026-01-31. "
                "1 row excluded because revenue was missing. "
                "1 row grouped under Unknown because region was missing."
            ),
        ),
    ]


def test_handle_slack_event_acknowledges_before_running_answer_path(
    canonical_question: str,
    connect_orders: testing_support.OrdersConnector,
) -> None:
    gateway = RecordingSlackGateway()
    payload: slack_boundary.SlackEventPayload = {
        "event_id": "Ev123",
        "event": {
            "type": "message",
            "channel": "C123",
            "user": "U123",
            "text": canonical_question,
            "ts": "1710000000.123456",
        },
    }
    order_rows = (("2026-01-03", "North", "1200.00"),)
    calls: list[str] = []

    def answer_path(
        connection: duckdb.DuckDBPyConnection,
        question: str,
    ) -> contracts.WorkflowResult:
        del connection
        assert question == canonical_question
        calls.append("answer_path")
        assert gateway.acknowledgements == 1
        return contracts.NonAnswer(
            stage="question_interpreter",
            reason="Need a time range.",
            unresolved_ambiguities=("time range",),
            next_step="Ask a clarification question before selecting data.",
        )

    with connect_orders(order_rows) as connection:
        slack_boundary.handle_slack_event(
            payload=payload,
            connection=connection,
            gateway=gateway,
            answer_path=answer_path,
        )

    assert gateway.acknowledgements == 1
    assert calls == ["answer_path"]
    assert gateway.calls == ["acknowledge", "deliver_response"]


def test_handle_slack_event_delivers_non_answer_response(
    connect_orders: testing_support.OrdersConnector,
) -> None:
    gateway = RecordingSlackGateway()
    payload: slack_boundary.SlackEventPayload = {
        "event_id": "Ev123",
        "event": {
            "type": "message",
            "channel": "C123",
            "user": "U123",
            "text": "What was total revenue by region?",
            "ts": "1710000000.123456",
        },
    }
    order_rows = (("2026-01-03", "North", "1200.00"),)

    with connect_orders(order_rows) as connection:
        slack_boundary.handle_slack_event(
            payload=payload,
            connection=connection,
            gateway=gateway,
        )

    assert len(gateway.deliveries) == 1
    assert (
        gateway.deliveries[0].text
        == "The Data Question is missing required interpretation details.\n\n"
        "Unresolved ambiguities: time range\n"
        "Next step: Ask a clarification question before selecting data."
    )


def test_handle_slack_event_returns_acknowledged_delivery_result(
    canonical_question: str,
    connect_orders: testing_support.OrdersConnector,
) -> None:
    gateway = RecordingSlackGateway()
    payload: slack_boundary.SlackEventPayload = {
        "event_id": "Ev123",
        "event": {
            "type": "message",
            "channel": "C123",
            "user": "U123",
            "text": canonical_question,
            "ts": "1710000000.123456",
        },
    }
    order_rows = (("2026-01-03", "North", "1200.00"),)

    with connect_orders(order_rows) as connection:
        result = slack_boundary.handle_slack_event(
            payload=payload,
            connection=connection,
            gateway=gateway,
        )

    assert result.acknowledged is True
    assert result.delivery == gateway.deliveries[0]

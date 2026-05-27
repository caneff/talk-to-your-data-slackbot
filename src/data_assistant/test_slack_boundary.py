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


def build_test_payload(
    *,
    event_id: str = "Ev123",
    event_type: str = "message",
    channel: str = "C123",
    user: str = "U123",
    text: str = "What was total revenue by region in January 2026?",
    ts: str = "1710000000.123456",
) -> slack_boundary.SlackEventPayload:
    return {
        "event_id": event_id,
        "event": {
            "type": event_type,
            "channel": channel,
            "user": user,
            "text": text,
            "ts": ts,
        },
    }


def resolve_employee_123_identity(
    _event: slack_boundary.SlackInnerEvent,
) -> contracts.InternalIdentity:
    return contracts.InternalIdentity(identity_id="employee_123")


def resolve_denied_identity(
    _event: slack_boundary.SlackInnerEvent,
) -> contracts.InternalIdentity:
    return contracts.InternalIdentity(identity_id="employee_denied")


def test_handle_slack_event_sends_answer_text_to_original_slack_thread(
    canonical_question: str,
    connect_orders: testing_support.OrdersConnector,
) -> None:
    gateway = RecordingSlackGateway()
    final_response = contracts.FinalResponse(
        text="Final answer text.",
        trust_summary=contracts.TrustSummary(datasets=("Commerce Revenue",)),
        response_kind="answer",
    )
    payload = build_test_payload(
        channel="C-final",
        text=canonical_question,
        ts="1710000000.654321",
    )
    order_rows = (("2026-01-03", "North", "1200.00"),)

    # The fake answer path keeps this test focused on Slack delivery, not
    # response composition or data retrieval.
    def answer_path(
        _connection: duckdb.DuckDBPyConnection,
        question: str,
        internal_identity: contracts.InternalIdentity,
    ) -> slack_boundary.SlackWorkflowResult:
        del internal_identity
        assert question == canonical_question
        return final_response

    with connect_orders(order_rows) as connection:
        slack_boundary.handle_slack_event(
            payload=payload,
            connection=connection,
            gateway=gateway,
            answer_path=answer_path,
        )

    assert len(gateway.deliveries) == 1
    delivery = gateway.deliveries[0]
    assert delivery.channel == "C-final"
    assert delivery.thread_ts == "1710000000.654321"
    assert delivery.text == final_response.text


def test_handle_slack_event_acknowledges_before_running_answer_path(
    canonical_question: str,
    connect_orders: testing_support.OrdersConnector,
) -> None:
    gateway = RecordingSlackGateway()
    payload = build_test_payload(text=canonical_question)
    order_rows = (("2026-01-03", "North", "1200.00"),)
    calls: list[str] = []

    def answer_path(
        _connection: duckdb.DuckDBPyConnection,
        question: str,
        internal_identity: contracts.InternalIdentity,
    ) -> slack_boundary.SlackWorkflowResult:
        del internal_identity
        assert question == canonical_question
        calls.append("answer_path")
        assert gateway.acknowledgements == 1
        return contracts.NonAnswer(
            stage=contracts.NonAnswerStage.QUESTION_INTERPRETER,
            reason_code=contracts.NonAnswerReasonCode.MISSING_REQUIRED_FIELD,
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
    payload = build_test_payload(text="What was total revenue by region?")
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
        == "I cannot answer safely yet because the Data Question is missing "
        "required interpretation details.\n\n"
        "Next step: Ask a clarification question before selecting data.\n\n"
        "Trust Summary: Limitations: The Data Question is missing required "
        "interpretation details."
    )


def test_handle_slack_event_returns_acknowledged_delivery_result(
    canonical_question: str,
    connect_orders: testing_support.OrdersConnector,
) -> None:
    gateway = RecordingSlackGateway()
    payload = build_test_payload(text=canonical_question)
    order_rows = (("2026-01-03", "North", "1200.00"),)

    with connect_orders(order_rows) as connection:
        result = slack_boundary.handle_slack_event(
            payload=payload,
            connection=connection,
            gateway=gateway,
            internal_identity_resolver=resolve_employee_123_identity,
        )

    assert result.acknowledged is True
    assert result.delivery == gateway.deliveries[0]


def test_handle_slack_event_passes_resolved_internal_identity_to_answer_path(
    canonical_question: str,
    connect_orders: testing_support.OrdersConnector,
) -> None:
    gateway = RecordingSlackGateway()
    payload = build_test_payload(user="U999", text=canonical_question)
    order_rows = (("2026-01-03", "North", "1200.00"),)
    seen_identity_ids: list[str] = []
    seen_slack_user_ids: list[str] = []

    def internal_identity_resolver(
        event: slack_boundary.SlackInnerEvent,
    ) -> contracts.InternalIdentity:
        seen_slack_user_ids.append(event["user"])
        return contracts.InternalIdentity(identity_id="employee_123")

    def answer_path(
        _connection: duckdb.DuckDBPyConnection,
        question: str,
        internal_identity: contracts.InternalIdentity,
    ) -> slack_boundary.SlackWorkflowResult:
        assert question == canonical_question
        seen_identity_ids.append(internal_identity.identity_id)
        return contracts.FinalResponse(
            text="Final answer text.",
            trust_summary=contracts.TrustSummary(datasets=("Commerce Revenue",)),
            response_kind="answer",
        )

    with connect_orders(order_rows) as connection:
        slack_boundary.handle_slack_event(
            payload=payload,
            connection=connection,
            gateway=gateway,
            answer_path=answer_path,
            internal_identity_resolver=internal_identity_resolver,
        )

    assert seen_slack_user_ids == ["U999"]
    assert seen_identity_ids == ["employee_123"]


def test_handle_slack_event_delivers_access_denial_for_denied_internal_identity(
    canonical_question: str,
    connect_orders: testing_support.OrdersConnector,
) -> None:
    gateway = RecordingSlackGateway()
    payload = build_test_payload(user="U999", text=canonical_question)
    order_rows = (("2026-01-03", "North", "1200.00"),)

    with connect_orders(order_rows) as connection:
        slack_boundary.handle_slack_event(
            payload=payload,
            connection=connection,
            gateway=gateway,
            internal_identity_resolver=resolve_denied_identity,
        )

    assert "commerce Curated Dataset" in gateway.deliveries[0].text
    assert "Dataset Table:" not in gateway.deliveries[0].text
    assert "Filters:" not in gateway.deliveries[0].text
    assert "Freshness:" not in gateway.deliveries[0].text

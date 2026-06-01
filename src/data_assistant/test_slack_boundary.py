from __future__ import annotations

import duckdb

import data_assistant.slack_boundary as slack_boundary
import data_assistant.workflow.contracts as contracts


class RecordingSlackGateway:
    def __init__(self) -> None:
        self.acknowledgements = 0
        self.calls: list[str] = []
        self.deliveries: list[slack_boundary.SlackDelivery] = []

    def acknowledge(self) -> None:
        self.calls.append("acknowledge")
        self.acknowledgements += 1

    def deliver_response(self, delivery: slack_boundary.SlackDelivery) -> None:
        self.calls.append("deliver_response")
        self.deliveries.append(delivery)


def _payload(
    *,
    channel: str = "C123",
    user: str = "U123",
    text: str = "What was total revenue by region in January 2026?",
    ts: str = "1710000000.123456",
) -> slack_boundary.SlackEventPayload:
    return {
        "event_id": "Ev123",
        "event": {
            "type": "message",
            "channel": channel,
            "user": user,
            "text": text,
            "ts": ts,
        },
    }


def _final_response(
    text: str = "Final answer text.",
    *,
    blocks: tuple[contracts.SlackBlock, ...] = (),
) -> contracts.FinalResponse:
    return contracts.FinalResponse(
        text=text,
        trust_summary=contracts.TrustSummary(datasets=("Commerce",)),
        response_kind=contracts.ResponseKind.ANSWER,
        blocks=blocks,
    )


def test_handle_slack_event_acknowledges_before_answer_and_returns_threaded_delivery(
    canonical_question: str,
) -> None:
    gateway = RecordingSlackGateway()
    final_response = _final_response()
    payload = _payload(
        channel="C-final",
        text=canonical_question,
        ts="1710000000.654321",
    )
    calls: list[str] = []

    def answer_path(
        _connection: duckdb.DuckDBPyConnection,
        question: str,
        internal_identity: contracts.InternalIdentity,
    ) -> slack_boundary.SlackWorkflowResult:
        del internal_identity
        assert question == canonical_question
        assert gateway.acknowledgements == 1
        calls.append("answer_path")
        return final_response

    with duckdb.connect(":memory:") as connection:
        result = slack_boundary.handle_slack_event(
            payload=payload,
            connection=connection,
            gateway=gateway,
            answer_path=answer_path,
        )

    delivery = slack_boundary.SlackDelivery(
        channel="C-final",
        thread_ts="1710000000.654321",
        text=final_response.text,
    )

    assert gateway.acknowledgements == 1
    assert calls == ["answer_path"]
    assert gateway.calls == ["acknowledge", "deliver_response"]
    assert gateway.deliveries == [delivery]
    assert result == slack_boundary.SlackRequestResult(
        acknowledged=True,
        delivery=delivery,
    )


def test_handle_slack_event_passes_resolved_internal_identity_to_answer_path(
    canonical_question: str,
) -> None:
    gateway = RecordingSlackGateway()
    payload = _payload(user="U999", text=canonical_question)
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
        return _final_response()

    with duckdb.connect(":memory:") as connection:
        slack_boundary.handle_slack_event(
            payload=payload,
            connection=connection,
            gateway=gateway,
            answer_path=answer_path,
            internal_identity_resolver=internal_identity_resolver,
        )

    assert seen_slack_user_ids == ["U999"]
    assert seen_identity_ids == ["employee_123"]


def test_handle_slack_event_carries_final_response_blocks_into_delivery(
    canonical_question: str,
) -> None:
    gateway = RecordingSlackGateway()
    blocks: tuple[contracts.SlackBlock, ...] = (
        {
            "type": "table",
            "rows": [
                [
                    {"type": "raw_text", "text": "Group"},
                    {"type": "raw_text", "text": "Value"},
                ],
            ],
        },
    )

    def answer_path(
        _connection: duckdb.DuckDBPyConnection,
        question: str,
        internal_identity: contracts.InternalIdentity,
    ) -> slack_boundary.SlackWorkflowResult:
        del internal_identity
        assert question == canonical_question
        return _final_response(blocks=blocks)

    with duckdb.connect(":memory:") as connection:
        result = slack_boundary.handle_slack_event(
            payload=_payload(text=canonical_question),
            connection=connection,
            gateway=gateway,
            answer_path=answer_path,
        )

    assert gateway.deliveries[0].blocks == blocks
    assert result.delivery.blocks == blocks

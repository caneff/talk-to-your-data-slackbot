"""Local Slack-like demo harness for the Data Assistant MVP."""

from __future__ import annotations

import dataclasses
import sys
import typing

import duckdb

import data_assistant.access_controller as access_controller
import data_assistant.slack_boundary as slack_boundary
import data_assistant.testing_support as testing_support
import data_assistant.workflow.contracts as contracts
import data_assistant.workflow.runner as workflow_runner

DEMO_ORDER_ROWS: tuple[testing_support.OrderRow, ...] = (
    ("2026-01-03", "North", "1200.00"),
    ("2026-01-10", "North", "300.00"),
    ("2026-01-12", "South", "800.00"),
    ("2026-01-20", None, "500.00"),
    ("2026-01-28", "West", None),
)


@dataclasses.dataclass(frozen=True)
class DemoScenarioResult:
    name: str
    request_text: str
    request_ts: str
    acknowledged: bool
    response_text: str
    response_thread_ts: str


@dataclasses.dataclass
class _RecordingSlackGateway:
    acknowledged: bool = False
    delivery: slack_boundary.SlackDelivery | None = None

    def acknowledge(self) -> None:
        self.acknowledged = True

    def deliver_response(self, delivery: slack_boundary.SlackDelivery) -> None:
        self.delivery = delivery


class _DemoQuestionInterpreterProvider:
    def propose_question_frame(
        self,
        *,
        question: str,
        prompt_context: dict[str, object],
    ) -> object:
        del prompt_context
        if question == "What was total revenue by region?":
            return {
                "intent": "summarize",
                "metric": "total revenue",
                "dimension": "region",
                "time_range": None,
                "filters": (),
            }
        return {
            "intent": "summarize",
            "metric": "total revenue",
            "dimension": "region",
            "time_range": {
                "label": "January 2026",
                "start_date": "2026-01-01",
                "end_date": "2026-01-31",
            },
            "filters": (),
        }


def run_demo() -> tuple[DemoScenarioResult, ...]:
    with testing_support.connect_orders(DEMO_ORDER_ROWS) as connection:
        return (
            _run_one_demo_scenario(
                name="happy_path",
                request_text="What was total revenue by region in January 2026?",
                request_ts="1710000000.100001",
                connection=connection,
            ),
            _run_one_demo_scenario(
                name="safe_non_answer",
                request_text="What was total revenue by region?",
                request_ts="1710000000.100002",
                connection=connection,
            ),
        )


def main(stdout: typing.TextIO = sys.stdout) -> int:
    for result in run_demo():
        _write_demo_scenario(stdout=stdout, result=result)
    return 0


def _run_one_demo_scenario(
    *,
    name: str,
    request_text: str,
    request_ts: str,
    connection: duckdb.DuckDBPyConnection,
) -> DemoScenarioResult:
    gateway = _RecordingSlackGateway()
    payload: slack_boundary.SlackEventPayload = {
        "event_id": f"Ev-{name}",
        "event": {
            "type": "message",
            "channel": "DDEMO",
            "user": "UDEMO",
            "text": request_text,
            "ts": request_ts,
        },
    }
    result = slack_boundary.handle_slack_event(
        payload=payload,
        connection=connection,
        gateway=gateway,
        answer_path=_run_demo_answer_path,
        internal_identity_resolver=_resolve_local_demo_identity,
    )
    if gateway.delivery is None:
        raise AssertionError("Demo scenario did not produce a Slack delivery.")
    return DemoScenarioResult(
        name=name,
        request_text=request_text,
        request_ts=request_ts,
        acknowledged=result.acknowledged,
        response_text=gateway.delivery.text,
        response_thread_ts=gateway.delivery.thread_ts,
    )


def _resolve_local_demo_identity(
    _event: slack_boundary.SlackInnerEvent,
) -> contracts.InternalIdentity:
    return access_controller.DEFAULT_LOCAL_ALLOWED_IDENTITY


def _run_demo_answer_path(
    connection: duckdb.DuckDBPyConnection,
    question: str,
    internal_identity: contracts.InternalIdentity,
) -> slack_boundary.SlackWorkflowResult:
    return workflow_runner.run_data_assistant(
        connection,
        question,
        question_interpreter_provider=_DemoQuestionInterpreterProvider(),
        internal_identity=internal_identity,
    )


def _write_demo_scenario(
    *,
    stdout: typing.TextIO,
    result: DemoScenarioResult,
) -> None:
    if result.name == "happy_path":
        stdout.write("Slack-like happy path request:\n")
        stdout.write(f"{result.request_text}\n")
        stdout.write("Slack Acknowledgement: 200 OK\n")
        stdout.write("threaded Final Response:\n")
        stdout.write(f"{result.response_text}\n\n")
        return

    stdout.write("Slack-like Non-Answer request:\n")
    stdout.write(f"{result.request_text}\n")
    stdout.write("Slack Acknowledgement: 200 OK\n")
    stdout.write("threaded Non-Answer Response:\n")
    stdout.write(f"{result.response_text}\n\n")


if __name__ == "__main__":
    raise SystemExit(main())

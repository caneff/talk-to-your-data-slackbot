"""Local Slack-like demo harness for the Data Assistant MVP."""

from __future__ import annotations

import dataclasses
import pathlib
import sys
import typing

import duckdb

import data_assistant.access_controller as access_controller
import data_assistant.local_duckdb_fixture as local_duckdb_fixture
import data_assistant.question_interpreter as question_interpreter
import data_assistant.question_interpreter.question_frame_cases as question_frame_cases
import data_assistant.slack_boundary as slack_boundary
import data_assistant.workflow.contracts as contracts
import data_assistant.workflow.runner as workflow_runner

_DEMO_SEED_PATH = pathlib.Path(__file__).parent / "seeds" / "demo_seed.sql"


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
    def __init__(self) -> None:
        self._proposals_by_question = {
            case.question: case.expected
            for case in question_frame_cases.SHARED_QUESTION_FRAME_CASES
        }

    def propose_question_frame(
        self,
        *,
        question: str,
        semantic_layer_context: dict[str, object],
    ) -> question_interpreter.QuestionFrameProposal:
        del semantic_layer_context
        return self._proposals_by_question[question]


def build_demo_question_interpreter_provider() -> (
    question_interpreter.QuestionInterpreterProvider
):
    """Build the fake Question Interpreter provider used by the local demo."""
    return _DemoQuestionInterpreterProvider()


def run_demo() -> tuple[DemoScenarioResult, ...]:
    with local_duckdb_fixture.connect_tables(
        (
            local_duckdb_fixture.orders_table_spec(()),
            local_duckdb_fixture.customers_table_spec(()),
        )
    ) as connection:
        connection.execute(_DEMO_SEED_PATH.read_text(encoding="utf-8"))
        return (
            _run_one_demo_scenario(
                name="happy_path",
                request_text="What was total revenue by region in January 2026?",
                request_ts="1710000000.100001",
                connection=connection,
            ),
            _run_one_demo_scenario(
                name="customer_count_by_region",
                request_text=(
                    "What was customer count by customer region in January 2026?"
                ),
                request_ts="1710000000.100002",
                connection=connection,
            ),
            _run_one_demo_scenario(
                name="safe_non_answer",
                request_text="What was total revenue by region?",
                request_ts="1710000000.100003",
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
        question_interpreter_provider=build_demo_question_interpreter_provider(),
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

"""Tests for the Slack Assistant surface adapter.

These tests exercise the pure ``AssistantAdapter`` with fake injected
``say`` / ``set_status`` / ``set_suggested_prompts`` callables. They never
construct a Bolt ``Assistant`` object or touch a live Slack API: the
``register_assistant_handlers`` Bolt wiring is a thin untested shim.
"""

from __future__ import annotations

import collections.abc
import contextlib
import logging

import duckdb
import pytest

import data_assistant.slack_assistant as slack_assistant
import data_assistant.workflow.contracts as contracts


class RecordingSay:
    """Capture ``say`` calls (text plus optional blocks)."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []

    def __call__(
        self,
        text: str,
        *,
        blocks: collections.abc.Sequence[contracts.SlackBlock] | None = None,
    ) -> None:
        self.calls.append((text, blocks))


class RecordingStatus:
    """Capture ``set_status`` calls."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def __call__(self, status: str) -> None:
        self.calls.append(status)


class RecordingSuggestedPrompts:
    """Capture ``set_suggested_prompts`` calls."""

    def __init__(self) -> None:
        self.calls: list[list[dict[str, str]]] = []

    def __call__(self, *, prompts: list[dict[str, str]]) -> None:
        self.calls.append(prompts)


def _final_response(
    text: str = "Final answer text.",
    *,
    blocks: tuple[contracts.SlackBlock, ...] = (),
    response_kind: contracts.ResponseKind = contracts.ResponseKind.ANSWER,
) -> contracts.FinalResponse:
    return contracts.FinalResponse(
        text=text,
        trust_summary=contracts.TrustSummary(datasets=("Commerce",)),
        response_kind=response_kind,
        blocks=blocks,
    )


def _connection_factory(
    connect_orders: collections.abc.Callable[
        ..., contextlib.AbstractContextManager[duckdb.DuckDBPyConnection]
    ],
) -> slack_assistant.ConnectionFactory:
    def factory() -> contextlib.AbstractContextManager[duckdb.DuckDBPyConnection]:
        return connect_orders((("2026-01-03", "North", "1200.00"),))

    return factory


def _unused_connection_factory() -> contextlib.AbstractContextManager[
    duckdb.DuckDBPyConnection
]:
    raise AssertionError("thread_started must not open a data connection")


def _unused_answer_path(
    _connection: duckdb.DuckDBPyConnection,
    _question: str,
    _identity: contracts.InternalIdentity,
) -> slack_assistant.SlackWorkflowResult:
    raise AssertionError("thread_started must not run the answer path")


def test_on_thread_started_posts_greeting_and_suggested_prompts() -> None:
    adapter = slack_assistant.AssistantAdapter(
        connection_factory=_unused_connection_factory,
        answer_path=_unused_answer_path,
    )
    say = RecordingSay()
    set_suggested_prompts = RecordingSuggestedPrompts()

    adapter.on_thread_started(say=say, set_suggested_prompts=set_suggested_prompts)

    assert say.calls == [(slack_assistant.GREETING, None)]
    assert set_suggested_prompts.calls == [
        [dict(prompt) for prompt in slack_assistant.SUGGESTED_PROMPTS]
    ]
    # The 3 provisional summarize-intent prompts are delivered dynamically.
    assert len(slack_assistant.SUGGESTED_PROMPTS) == 3
    for prompt in set_suggested_prompts.calls[0]:
        assert set(prompt) == {"title", "message"}


def test_on_user_message_sets_status_runs_pipeline_then_says(
    canonical_question: str,
    connect_orders: collections.abc.Callable[
        ..., contextlib.AbstractContextManager[duckdb.DuckDBPyConnection]
    ],
) -> None:
    say = RecordingSay()
    set_status = RecordingStatus()
    calls: list[str] = []
    seen_questions: list[str] = []
    blocks: tuple[contracts.SlackBlock, ...] = (
        {"type": "section", "text": {"type": "mrkdwn", "text": "trust"}},
    )

    def answer_path(
        _connection: duckdb.DuckDBPyConnection,
        question: str,
        _identity: contracts.InternalIdentity,
    ) -> slack_assistant.SlackWorkflowResult:
        # set_status must already have fired before the pipeline runs.
        assert set_status.calls == [slack_assistant.ANALYZING_STATUS]
        calls.append("answer_path")
        seen_questions.append(question)
        return _final_response(blocks=blocks)

    adapter = slack_assistant.AssistantAdapter(
        connection_factory=_connection_factory(connect_orders),
        answer_path=answer_path,
    )

    adapter.on_user_message(
        text=canonical_question,
        user="U123",
        channel="D123",
        thread_ts="1710000000.654321",
        set_status=set_status,
        say=say,
    )

    assert set_status.calls == [slack_assistant.ANALYZING_STATUS]
    assert calls == ["answer_path"]
    assert seen_questions == [canonical_question]
    assert say.calls == [("Final answer text.", blocks)]


def test_on_user_message_says_non_answer_without_fallback(
    connect_orders: collections.abc.Callable[
        ..., contextlib.AbstractContextManager[duckdb.DuckDBPyConnection]
    ],
) -> None:
    """A Non-Answer renders like any other Final Response: no crash, no fallback."""
    say = RecordingSay()
    set_status = RecordingStatus()
    non_answer = _final_response(
        text="I can't answer that from the approved data.",
        response_kind=contracts.ResponseKind.UNSUPPORTED,
    )

    def answer_path(
        _connection: duckdb.DuckDBPyConnection,
        _question: str,
        _identity: contracts.InternalIdentity,
    ) -> slack_assistant.SlackWorkflowResult:
        return non_answer

    adapter = slack_assistant.AssistantAdapter(
        connection_factory=_connection_factory(connect_orders),
        answer_path=answer_path,
    )

    adapter.on_user_message(
        text="something unsupported",
        user="U123",
        channel="D123",
        thread_ts="1710000000.654321",
        set_status=set_status,
        say=say,
    )

    assert say.calls == [(non_answer.text, None)]
    assert slack_assistant.RUNTIME_FALLBACK_MESSAGE not in [c[0] for c in say.calls]


def test_on_user_message_says_runtime_fallback_on_crash_without_raising(
    connect_orders: collections.abc.Callable[
        ..., contextlib.AbstractContextManager[duckdb.DuckDBPyConnection]
    ],
) -> None:
    say = RecordingSay()
    set_status = RecordingStatus()

    def answer_path(
        _connection: duckdb.DuckDBPyConnection,
        _question: str,
        _identity: contracts.InternalIdentity,
    ) -> slack_assistant.SlackWorkflowResult:
        raise RuntimeError("answer path blew up: secret-value=9999")

    adapter = slack_assistant.AssistantAdapter(
        connection_factory=_connection_factory(connect_orders),
        answer_path=answer_path,
    )

    # The adapter must swallow the exception and reply with the fallback.
    adapter.on_user_message(
        text="What was total revenue last quarter?",
        user="U123",
        channel="D123",
        thread_ts="1710000000.654321",
        set_status=set_status,
        say=say,
    )

    assert say.calls == [(slack_assistant.RUNTIME_FALLBACK_MESSAGE, None)]
    fallback_text = say.calls[0][0]
    assert "secret-value" not in fallback_text
    assert "RuntimeError" not in fallback_text
    assert "total revenue last quarter" not in fallback_text


def test_on_user_message_logs_failure_metadata_for_maintainers(
    caplog: pytest.LogCaptureFixture,
    connect_orders: collections.abc.Callable[
        ..., contextlib.AbstractContextManager[duckdb.DuckDBPyConnection]
    ],
) -> None:
    """One ERROR log carries routing metadata, exception type, and question text."""
    say = RecordingSay()
    set_status = RecordingStatus()

    def answer_path(
        _connection: duckdb.DuckDBPyConnection,
        _question: str,
        _identity: contracts.InternalIdentity,
    ) -> slack_assistant.SlackWorkflowResult:
        raise RuntimeError("connection blew up")

    adapter = slack_assistant.AssistantAdapter(
        connection_factory=_connection_factory(connect_orders),
        answer_path=answer_path,
    )

    with caplog.at_level(logging.ERROR, logger=slack_assistant.logger.name):
        adapter.on_user_message(
            text="What was total revenue last quarter?",
            user="U123",
            channel="D123",
            thread_ts="1710000000.654321",
            set_status=set_status,
            say=say,
        )

    records = [
        record
        for record in caplog.records
        if record.name == slack_assistant.logger.name
    ]
    assert len(records) == 1
    record = records[0]
    assert record.levelno == logging.ERROR
    message = record.getMessage()
    assert "D123" in message
    assert "1710000000.654321" in message
    assert "U123" in message
    assert "RuntimeError" in message
    assert "What was total revenue last quarter?" in message
    assert record.exc_info is not None


def test_on_user_message_passes_resolved_identity_to_answer_path(
    connect_orders: collections.abc.Callable[
        ..., contextlib.AbstractContextManager[duckdb.DuckDBPyConnection]
    ],
) -> None:
    say = RecordingSay()
    set_status = RecordingStatus()
    seen_identity_ids: list[str] = []

    def answer_path(
        _connection: duckdb.DuckDBPyConnection,
        _question: str,
        identity: contracts.InternalIdentity,
    ) -> slack_assistant.SlackWorkflowResult:
        seen_identity_ids.append(identity.identity_id)
        return _final_response()

    adapter = slack_assistant.AssistantAdapter(
        connection_factory=_connection_factory(connect_orders),
        answer_path=answer_path,
    )

    adapter.on_user_message(
        text="any question",
        user="U999",
        channel="D123",
        thread_ts="1710000000.654321",
        set_status=set_status,
        say=say,
    )

    # The default resolver maps the Slack user id into the workflow contract.
    assert seen_identity_ids == ["slack_user:U999"]


def test_default_identity_maps_slack_user() -> None:
    identity = slack_assistant._default_identity("U777")  # pyright: ignore[reportPrivateUsage]
    assert identity == contracts.InternalIdentity(identity_id="slack_user:U777")


def test_dev_identity_uses_local_allowed_identity() -> None:
    import data_assistant.access_controller as access_controller

    identity = slack_assistant._dev_identity("U777")  # pyright: ignore[reportPrivateUsage]
    assert identity == access_controller.DEFAULT_LOCAL_ALLOWED_IDENTITY


def test_custom_identity_resolver_is_used(
    connect_orders: collections.abc.Callable[
        ..., contextlib.AbstractContextManager[duckdb.DuckDBPyConnection]
    ],
) -> None:
    say = RecordingSay()
    set_status = RecordingStatus()
    seen_users: list[str] = []
    seen_identity_ids: list[str] = []

    def resolver(user: str) -> contracts.InternalIdentity:
        seen_users.append(user)
        return contracts.InternalIdentity(identity_id="employee_123")

    def answer_path(
        _connection: duckdb.DuckDBPyConnection,
        _question: str,
        identity: contracts.InternalIdentity,
    ) -> slack_assistant.SlackWorkflowResult:
        seen_identity_ids.append(identity.identity_id)
        return _final_response()

    adapter = slack_assistant.AssistantAdapter(
        connection_factory=_connection_factory(connect_orders),
        answer_path=answer_path,
        internal_identity_resolver=resolver,
    )

    adapter.on_user_message(
        text="any question",
        user="U999",
        channel="D123",
        thread_ts="1710000000.654321",
        set_status=set_status,
        say=say,
    )

    assert seen_users == ["U999"]
    assert seen_identity_ids == ["employee_123"]


def test_final_response_from_workflow_result_unwraps_run() -> None:
    final = _final_response(text="unwrapped")
    run = contracts.DataAssistantRun  # type alias smoke

    # A bare FinalResponse passes through unchanged.
    assert slack_assistant.final_response_from_workflow_result(final) is final
    del run

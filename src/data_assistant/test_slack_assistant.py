"""Tests for the Slack Assistant surface adapter.

These tests exercise the pure ``AssistantAdapter`` with fake injected
``say`` / ``set_status`` / ``set_suggested_prompts`` callables. They never
construct a Bolt ``Assistant`` object or touch a live Slack API: the
``register_assistant_handlers`` Bolt wiring is a thin untested shim.
"""

from __future__ import annotations

import collections.abc
import contextlib
import datetime
import json
import logging
import pathlib

import duckdb
import pandas as pd
import pytest

import data_assistant.semantic_layer.schema as schema
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
    identity = slack_assistant.default_identity("U777")
    assert identity == contracts.InternalIdentity(identity_id="slack_user:U777")


def test_dev_identity_uses_local_allowed_identity() -> None:
    import data_assistant.access_controller as access_controller

    identity = slack_assistant.dev_identity("U777")
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


# --- Interaction Log capture (ADR-0016) -------------------------------------


def _curated_dataset() -> schema.CuratedDataset:
    return schema.CuratedDataset(
        dataset_id="commerce",
        name="Commerce",
        tables=("orders",),
        information_types=("orders",),
        freshness=schema.Freshness(
            as_of=datetime.date(2026, 1, 31),
            description="Commerce order data refreshed daily.",
        ),
        example_questions=("What was revenue by region?",),
    )


def _dataset_table() -> schema.DatasetTable:
    return schema.DatasetTable(
        table_id="orders",
        dataset_id="commerce",
        description="Order facts.",
        columns=(
            schema.TableColumn(column_id="region", data_type="string"),
            schema.TableColumn(column_id="net_revenue", data_type="decimal"),
            schema.TableColumn(column_id="order_date", data_type="date"),
        ),
        metrics=(
            schema.Metric(
                metric_id="total_revenue",
                label="total revenue",
                expression="SUM(net_revenue)",
                source_column="net_revenue",
                kind=schema.MetricKind.MONEY,
            ),
        ),
        fields=(
            schema.SemanticField(
                field_id="region",
                label="region",
                source_column="region",
                data_type=schema.DataType.STRING,
                operations=(schema.FieldOperation.GROUP_BY,),
            ),
            schema.SemanticField(
                field_id="order_date",
                label="order date",
                source_column="order_date",
                data_type=schema.DataType.DATE,
                operations=(schema.FieldOperation.RANGE_FILTER,),
            ),
        ),
    )


def _data_assistant_run() -> contracts.DataAssistantRun:
    dataset = _curated_dataset()
    table = _dataset_table()
    metric = table.metrics[0]
    region_field = table.fields[0]
    order_date_field = table.fields[1]
    question_frame = contracts.QuestionFrame(
        intent="summarize",
        metric="total revenue",
        time_scope=contracts.TimeScope.BOUNDED,
        field_operations=(
            contracts.SemanticFieldOperation(
                operation=schema.FieldOperation.GROUP_BY,
                field="region",
            ),
        ),
        unresolved_ambiguities=(),
    )
    match = contracts.SemanticMatch(
        dataset=dataset,
        table=table,
        metric=metric,
        group_by_fields=(region_field,),
    )
    data_request = contracts.DataRequest(
        dataset=dataset,
        table=table,
        metric=metric,
        group_by_fields=(region_field,),
        filter_operations=(
            contracts.ResolvedSemanticFieldOperation(
                operation=schema.FieldOperation.RANGE_FILTER,
                field=order_date_field,
                lower=datetime.date(2026, 1, 1),
                upper=datetime.date(2026, 1, 31),
            ),
        ),
        output_shape="total revenue grouped by region",
        result_limit=10,
    )
    prepared_data = contracts.PreparedData(
        request=data_request,
        # SECRET / sensitive cell values that must NEVER reach the log.
        data=pd.DataFrame(
            {
                "region": ("North", "South", "Acme-Secret-Corp"),
                "net_revenue": (1200.0, 850.0, 99999.0),
            }
        ),
        quality_notes=("1 row excluded because revenue was missing.",),
    )
    answer_draft = contracts.AnswerDraft(
        summary="Total revenue in January 2026 was $2,050.00.",
        key_data=pd.DataFrame(
            {
                "dimension_value": ("North", "South"),
                "metric_value": (1200.0, 850.0),
            }
        ),
        datasets_used=("Commerce",),
        dataset_tables_used=("orders",),
        metric_kind=schema.MetricKind.MONEY,
        metric_label="total revenue",
        time_range="January 2026",
        filters=("order date >= 2026-01-01 and <= 2026-01-31",),
        freshness="Commerce order data refreshed through 2026-01-31.",
        caveats=(),
        group_by_label="region",
    )
    final_response = contracts.FinalResponse(
        text="Total revenue in January 2026 was $2,050.00.",
        trust_summary=contracts.TrustSummary(datasets=("Commerce",)),
        response_kind=contracts.ResponseKind.ANSWER,
    )
    return contracts.DataAssistantRun(
        question_frame=question_frame,
        available_data_resolution=contracts.AvailableDataResolution(
            resolved_match=match,
            dataset_selection=contracts.DatasetSelection(
                selected_datasets=(dataset,),
                match_rationale="single match",
            ),
        ),
        data_request=data_request,
        prepared_data=prepared_data,
        answer_draft=answer_draft,
        final_response=final_response,
    )


def _read_log_records(log_path: pathlib.Path) -> list[dict[str, object]]:
    return [
        json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()
    ]


def _run_adapter(
    *,
    log_path: pathlib.Path,
    connect_orders: collections.abc.Callable[
        ..., contextlib.AbstractContextManager[duckdb.DuckDBPyConnection]
    ],
    answer_path: slack_assistant.AnswerPath,
    text: str = "What was total revenue by region in January 2026?",
) -> None:
    adapter = slack_assistant.AssistantAdapter(
        connection_factory=_connection_factory(connect_orders),
        answer_path=answer_path,
        model_label="gpt-4o-mini",
        log_path=log_path,
    )
    adapter.on_user_message(
        text=text,
        user="U123",
        channel="D123",
        thread_ts="1710000000.654321",
        set_status=RecordingStatus(),
        say=RecordingSay(),
    )


def test_on_user_message_logs_answer_record_with_shape_and_key_data(
    tmp_path: pathlib.Path,
    connect_orders: collections.abc.Callable[
        ..., contextlib.AbstractContextManager[duckdb.DuckDBPyConnection]
    ],
) -> None:
    log_path = tmp_path / "interactions.jsonl"
    run = _data_assistant_run()

    def answer_path(
        _connection: duckdb.DuckDBPyConnection,
        _question: str,
        _identity: contracts.InternalIdentity,
    ) -> slack_assistant.SlackWorkflowResult:
        return run

    _run_adapter(
        log_path=log_path,
        connect_orders=connect_orders,
        answer_path=answer_path,
    )

    records = _read_log_records(log_path)
    assert len(records) == 1
    record = records[0]
    assert record["outcome"] == "answer"
    assert record["model"] == "gpt-4o-mini"
    assert record["user"] == "U123"
    assert record["flags"] == []
    assert record["question"] == "What was total revenue by region in January 2026?"
    assert isinstance(record["id"], str) and record["id"]
    assert isinstance(record["latency_ms"], int)
    assert record["intent"] == "summarize"
    assert record["dataset"] == "Commerce"
    assert record["metric"] == "total revenue"
    assert record["group_by"] == ["region"]
    assert record["result_limit"] == 10
    # Prepared-data SHAPE only -- rows x columns + quality notes.
    assert record["prepared_data_shape"] == {"rows": 3, "columns": 2}
    assert record["quality_notes"] == ["1 row excluded because revenue was missing."]
    # key_data headline numbers ARE included (ADR-0016 deliberate inclusion).
    assert record["key_data"] == [
        {"dimension_value": "North", "metric_value": 1200.0},
        {"dimension_value": "South", "metric_value": 850.0},
    ]
    # Sanitization: NO raw Prepared Data cell values anywhere in the line.
    # (The metric EXPRESSION -- e.g. SUM(net_revenue) -- is deliberately kept as
    # debug signal; only Prepared Data *cell values* are excluded.)
    serialized = json.dumps(record)
    assert "Acme-Secret-Corp" not in serialized
    assert "99999" not in serialized


def test_on_user_message_logs_non_answer_record_with_reason_and_stage(
    tmp_path: pathlib.Path,
    connect_orders: collections.abc.Callable[
        ..., contextlib.AbstractContextManager[duckdb.DuckDBPyConnection]
    ],
) -> None:
    log_path = tmp_path / "interactions.jsonl"
    non_answer = contracts.NonAnswer(
        stage=contracts.NonAnswerStage.QUESTION_INTERPRETER,
        reason_code=contracts.NonAnswerReasonCode.MISSING_TIME_SCOPE,
        context=("order date",),
    )
    final = contracts.FinalResponse(
        text="I cannot answer safely yet because ...",
        trust_summary=contracts.TrustSummary(),
        response_kind=contracts.ResponseKind.CLARIFICATION_NEEDED,
        non_answer=non_answer,
    )

    def answer_path(
        _connection: duckdb.DuckDBPyConnection,
        _question: str,
        _identity: contracts.InternalIdentity,
    ) -> slack_assistant.SlackWorkflowResult:
        return final

    _run_adapter(
        log_path=log_path,
        connect_orders=connect_orders,
        answer_path=answer_path,
    )

    records = _read_log_records(log_path)
    assert len(records) == 1
    record = records[0]
    assert record["outcome"] == "non_answer"
    assert record["reason_code"] == "missing_time_scope"
    assert record["stage"] == "question_interpreter"
    assert record["context"] == ["order date"]
    assert record["response_text"] == "I cannot answer safely yet because ..."
    assert record["flags"] == []


def test_on_user_message_logs_error_record_and_still_says_fallback(
    tmp_path: pathlib.Path,
    connect_orders: collections.abc.Callable[
        ..., contextlib.AbstractContextManager[duckdb.DuckDBPyConnection]
    ],
) -> None:
    log_path = tmp_path / "interactions.jsonl"
    say = RecordingSay()

    def answer_path(
        _connection: duckdb.DuckDBPyConnection,
        _question: str,
        _identity: contracts.InternalIdentity,
    ) -> slack_assistant.SlackWorkflowResult:
        raise RuntimeError("answer path blew up")

    adapter = slack_assistant.AssistantAdapter(
        connection_factory=_connection_factory(connect_orders),
        answer_path=answer_path,
        model_label="gpt-4o-mini",
        log_path=log_path,
    )
    adapter.on_user_message(
        text="What was total revenue last quarter?",
        user="U123",
        channel="D123",
        thread_ts="1710000000.654321",
        set_status=RecordingStatus(),
        say=say,
    )

    # The user still gets the Runtime Fallback reply.
    assert say.calls == [(slack_assistant.RUNTIME_FALLBACK_MESSAGE, None)]
    records = _read_log_records(log_path)
    assert len(records) == 1
    record = records[0]
    assert record["outcome"] == "error"
    assert record["error_type"] == "RuntimeError"
    assert record["error_message"] == "answer path blew up"
    assert record["flags"] == []


def test_on_user_message_log_failure_does_not_break_user_reply(
    tmp_path: pathlib.Path,
    connect_orders: collections.abc.Callable[
        ..., contextlib.AbstractContextManager[duckdb.DuckDBPyConnection]
    ],
) -> None:
    """A logging failure must never prevent the user-facing reply."""
    # Point the log at a path that cannot be created (a file used as a dir).
    blocker = tmp_path / "blocker"
    blocker.write_text("not a directory", encoding="utf-8")
    unwritable_log = blocker / "interactions.jsonl"
    say = RecordingSay()

    def answer_path(
        _connection: duckdb.DuckDBPyConnection,
        _question: str,
        _identity: contracts.InternalIdentity,
    ) -> slack_assistant.SlackWorkflowResult:
        return _final_response(text="Answer text.")

    adapter = slack_assistant.AssistantAdapter(
        connection_factory=_connection_factory(connect_orders),
        answer_path=answer_path,
        model_label="gpt-4o-mini",
        log_path=unwritable_log,
    )

    adapter.on_user_message(
        text="any question",
        user="U123",
        channel="D123",
        thread_ts="1710000000.654321",
        set_status=RecordingStatus(),
        say=say,
    )

    # The reply still went out even though the log write failed.
    assert say.calls == [("Answer text.", None)]


def test_on_user_message_record_build_failure_does_not_break_user_reply(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: pathlib.Path,
    connect_orders: collections.abc.Callable[
        ..., contextlib.AbstractContextManager[duckdb.DuckDBPyConnection]
    ],
) -> None:
    """A failure to BUILD the record must not suppress a good answer.

    Record construction (``to_dict`` / ``.shape`` / field extraction) must run
    inside the same swallow as the append, so a malformed trace logs an error
    and is dropped -- the user still gets the real answer, not the fallback.
    """
    log_path = tmp_path / "interactions.jsonl"
    say = RecordingSay()
    run = _data_assistant_run()

    def boom(**_kwargs: object) -> dict[str, object]:
        raise ValueError("record construction blew up")

    monkeypatch.setattr(slack_assistant, "_interaction_record", boom)

    def answer_path(
        _connection: duckdb.DuckDBPyConnection,
        _question: str,
        _identity: contracts.InternalIdentity,
    ) -> slack_assistant.SlackWorkflowResult:
        return run

    adapter = slack_assistant.AssistantAdapter(
        connection_factory=_connection_factory(connect_orders),
        answer_path=answer_path,
        model_label="gpt-4o-mini",
        log_path=log_path,
    )

    adapter.on_user_message(
        text="any question",
        user="U123",
        channel="D123",
        thread_ts="1710000000.654321",
        set_status=RecordingStatus(),
        say=say,
    )

    # The user gets the REAL answer (not the Runtime Fallback), no exception
    # escapes, and nothing was written.
    assert say.calls == [(run.final_response.text, run.final_response.blocks or None)]
    assert say.calls[0][0] != slack_assistant.RUNTIME_FALLBACK_MESSAGE
    assert not log_path.exists()

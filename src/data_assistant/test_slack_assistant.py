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
import typing

import duckdb
import pandas as pd
import pytest

import data_assistant.assistant_thread_pointer as assistant_thread_pointer
import data_assistant.interaction_log as interaction_log
import data_assistant.interaction_record as interaction_record
import data_assistant.known_qa_issues as known_qa_issues
import data_assistant.semantic_layer.schema as schema
import data_assistant.slack_assistant as slack_assistant
import data_assistant.workflow.contracts as contracts

EXPECTED_PROGRESS_STATUSES = [
    "understanding your question...",
    "finding the right data...",
    "running the numbers...",
    "writing it up...",
]


def _action_ids_in(
    blocks: collections.abc.Sequence[contracts.SlackBlock],
) -> set[str]:
    """Collect every button ``action_id`` across all ``actions`` blocks."""
    action_ids: set[str] = set()
    for block in blocks:
        if block.get("type") != "actions":
            continue
        for element in _button_elements(block):
            action_id = element["action_id"]
            assert isinstance(action_id, str)
            action_ids.add(action_id)
    return action_ids


def _section_texts_in(
    blocks: collections.abc.Sequence[contracts.SlackBlock],
) -> list[str]:
    """Collect visible text from Slack section blocks."""
    texts: list[str] = []
    for block in blocks:
        if block.get("type") != "section":
            continue
        text = block.get("text")
        assert isinstance(text, dict)
        typed_text = typing.cast("dict[str, object]", text)
        value = typed_text.get("text")
        assert isinstance(value, str)
        texts.append(value)
    return texts


def _context_text(block: contracts.SlackBlock) -> str:
    """Narrow a ``context`` block's first mrkdwn element to its text."""
    assert block.get("type") == "context"
    elements = block.get("elements")
    assert isinstance(elements, list) and elements
    first = typing.cast("list[object]", elements)[0]
    assert isinstance(first, dict)
    text = typing.cast("dict[str, object]", first).get("text")
    assert isinstance(text, str)
    return text


def _button_elements(block: contracts.SlackBlock) -> list[dict[str, object]]:
    """Narrow an ``actions`` block's ``elements`` to a typed list of buttons."""
    elements = block.get("elements")
    assert isinstance(elements, list)
    typed: list[dict[str, object]] = []
    for element in typing.cast("list[object]", elements):
        assert isinstance(element, dict)
        button = typing.cast("dict[str, object]", element)
        typed.append(button)
    return typed


def _actions_blocks(
    blocks: collections.abc.Sequence[contracts.SlackBlock],
) -> list[contracts.SlackBlock]:
    return [block for block in blocks if block.get("type") == "actions"]


class RecordingSay:
    """Capture ``say`` calls (text plus optional blocks)."""

    def __init__(self) -> None:
        self.calls: list[
            tuple[str, collections.abc.Sequence[contracts.SlackBlock] | None]
        ] = []

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
        trust_summary=contracts.TrustSummary(datasets=("Retail Operations",)),
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
    _progress_sink: contracts.ProgressSink,
) -> slack_assistant.SlackWorkflowResult:
    raise AssertionError("thread_started must not run the answer path")


def test_on_thread_started_posts_greeting_and_suggested_prompts(
    tmp_path: pathlib.Path,
) -> None:
    adapter = slack_assistant.AssistantAdapter(
        connection_factory=_unused_connection_factory,
        answer_path=_unused_answer_path,
        pointer_path=tmp_path / "last_assistant_thread.json",
    )
    say = RecordingSay()
    set_suggested_prompts = RecordingSuggestedPrompts()

    adapter.on_thread_started(
        say=say,
        set_suggested_prompts=set_suggested_prompts,
        channel="C123",
        thread_ts="1748880000.123456",
    )

    assert say.calls == [(slack_assistant.GREETING, None)]
    assert set_suggested_prompts.calls == [
        [dict(prompt) for prompt in slack_assistant.SUGGESTED_PROMPTS]
    ]
    # The 3 provisional summarize-intent prompts are delivered dynamically.
    assert len(slack_assistant.SUGGESTED_PROMPTS) == 3
    for prompt in set_suggested_prompts.calls[0]:
        assert set(prompt) == {"title", "message"}


def test_on_thread_started_writes_assistant_thread_pointer(
    tmp_path: pathlib.Path,
) -> None:
    pointer_path = tmp_path / "last_assistant_thread.json"
    adapter = slack_assistant.AssistantAdapter(
        connection_factory=_unused_connection_factory,
        answer_path=_unused_answer_path,
        pointer_path=pointer_path,
    )

    adapter.on_thread_started(
        say=RecordingSay(),
        set_suggested_prompts=RecordingSuggestedPrompts(),
        channel="C123",
        thread_ts="1748880000.123456",
    )

    # The QA driver later reads this to auto-discover the thread.
    assert assistant_thread_pointer.read_latest(pointer_path) == (
        "C123",
        "1748880000.123456",
    )


def test_on_thread_started_greets_even_if_pointer_write_fails(
    tmp_path: pathlib.Path,
) -> None:
    """A pointer-write failure must NEVER break the greeting/suggested prompts.

    Same 'reply wins' boundary as the Interaction Log capture: best-effort
    discovery state is strictly subordinate to the user-facing greeting.
    """
    # Point at a path that cannot be created (a file used as a directory).
    blocker = tmp_path / "blocker"
    blocker.write_text("not a directory", encoding="utf-8")
    adapter = slack_assistant.AssistantAdapter(
        connection_factory=_unused_connection_factory,
        answer_path=_unused_answer_path,
        pointer_path=blocker / "last_assistant_thread.json",
    )
    say = RecordingSay()
    set_suggested_prompts = RecordingSuggestedPrompts()

    adapter.on_thread_started(
        say=say,
        set_suggested_prompts=set_suggested_prompts,
        channel="C123",
        thread_ts="1748880000.123456",
    )

    # Greeting + suggested prompts still went out despite the failed write.
    assert say.calls == [(slack_assistant.GREETING, None)]
    assert len(set_suggested_prompts.calls) == 1


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
        progress_sink: contracts.ProgressSink,
    ) -> slack_assistant.SlackWorkflowResult:
        assert set_status.calls == []
        progress_sink(EXPECTED_PROGRESS_STATUSES[0])
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

    assert set_status.calls == [EXPECTED_PROGRESS_STATUSES[0]]
    assert calls == ["answer_path"]
    assert seen_questions == [canonical_question]
    assert len(say.calls) == 1
    said_text, said_blocks = say.calls[0]
    assert said_text == "Final answer text."
    # Every reply leads with the question echo; the original trust-summary block
    # is preserved after it, with the flag actions block appended so every reply
    # is flaggable.
    assert said_blocks is not None
    said_blocks = tuple(said_blocks)
    assert said_blocks[0]["type"] == "context"
    assert _context_text(said_blocks[0]) == "❓ " + canonical_question
    assert said_blocks[1 : 1 + len(blocks)] == blocks
    assert _action_ids_in(said_blocks) == {
        slack_assistant.FLAG_CORRECTNESS_ACTION_ID,
        slack_assistant.FLAG_FORMATTING_ACTION_ID,
        slack_assistant.FLAG_INVESTIGATE_ACTION_ID,
    }


def test_on_user_message_uses_pipeline_progress_sink_for_staged_status(
    canonical_question: str,
    connect_orders: collections.abc.Callable[
        ..., contextlib.AbstractContextManager[duckdb.DuckDBPyConnection]
    ],
) -> None:
    say = RecordingSay()
    set_status = RecordingStatus()
    seen_questions: list[str] = []

    def answer_path(
        _connection: duckdb.DuckDBPyConnection,
        question: str,
        _identity: contracts.InternalIdentity,
        progress_sink: contracts.ProgressSink,
    ) -> slack_assistant.SlackWorkflowResult:
        seen_questions.append(question)
        for status in EXPECTED_PROGRESS_STATUSES:
            progress_sink(status)
        return _final_response()

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

    assert seen_questions == [canonical_question]
    assert set_status.calls == EXPECTED_PROGRESS_STATUSES
    assert len(say.calls) == 1
    said_text, said_blocks = say.calls[0]
    assert said_text == "Final answer text."
    # Slack does not display `text` when blocks are present, so a plain
    # FinalResponse needs a synthesized text section before the flag buttons.
    assert said_blocks is not None
    assert _section_texts_in(tuple(said_blocks)) == ["Final answer text."]
    assert _action_ids_in(tuple(said_blocks)) == {
        slack_assistant.FLAG_CORRECTNESS_ACTION_ID,
        slack_assistant.FLAG_FORMATTING_ACTION_ID,
        slack_assistant.FLAG_INVESTIGATE_ACTION_ID,
    }


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
        _progress_sink: contracts.ProgressSink,
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

    assert len(say.calls) == 1
    said_text, said_blocks = say.calls[0]
    assert said_text == non_answer.text
    # A Non-Answer is visible and also flaggable (e.g. flag a spurious refusal).
    assert said_blocks is not None
    assert _section_texts_in(tuple(said_blocks)) == [non_answer.text]
    assert _action_ids_in(tuple(said_blocks)) == {
        slack_assistant.FLAG_CORRECTNESS_ACTION_ID,
        slack_assistant.FLAG_FORMATTING_ACTION_ID,
        slack_assistant.FLAG_INVESTIGATE_ACTION_ID,
    }
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
        _progress_sink: contracts.ProgressSink,
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

    assert len(say.calls) == 1
    fallback_text, fallback_blocks = say.calls[0]
    assert fallback_text == slack_assistant.RUNTIME_FALLBACK_MESSAGE
    # The crash reply is itself flaggable (its record exists with outcome=error).
    assert fallback_blocks is not None
    fallback_blocks = tuple(fallback_blocks)
    # The crash reply also leads with the question echo so it stays pairable.
    assert fallback_blocks[0]["type"] == "context"
    assert (
        _context_text(fallback_blocks[0]) == "❓ What was total revenue last quarter?"
    )
    assert _action_ids_in(tuple(fallback_blocks)) == {
        slack_assistant.FLAG_CORRECTNESS_ACTION_ID,
        slack_assistant.FLAG_FORMATTING_ACTION_ID,
        slack_assistant.FLAG_INVESTIGATE_ACTION_ID,
    }
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
        _progress_sink: contracts.ProgressSink,
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
        _progress_sink: contracts.ProgressSink,
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
        _progress_sink: contracts.ProgressSink,
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


# --- Interaction Log capture (ADR-0016) -------------------------------------


def _curated_dataset() -> schema.CuratedDataset:
    return schema.CuratedDataset(
        dataset_id="retail_ops",
        name="Retail Operations",
        tables=("orders",),
        information_types=("orders",),
        example_questions=("What was revenue by region?",),
    )


def _dataset_table() -> schema.DatasetTable:
    return schema.DatasetTable(
        table_id="orders",
        dataset_id="retail_ops",
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
        group_by_field="region",
        field_filters=(),
        unresolved_ambiguities=(),
    )
    match = contracts.SemanticMatch(
        dataset=dataset,
        table=table,
        metric=metric,
        group_by_field=region_field,
        field_filters=(),
    )
    data_request = contracts.DataRequest(
        dataset=dataset,
        table=table,
        metric=metric,
        group_by_field=region_field,
        field_filters=(
            contracts.RangeFilter(
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
        datasets_used=("Retail Operations",),
        dataset_tables_used=("orders",),
        metric_kind=schema.MetricKind.MONEY,
        metric_label="total revenue",
        time_range="January 2026",
        filters=("order date >= 2026-01-01 and <= 2026-01-31",),
        caveats=(),
        group_by_label="region",
    )
    final_response = contracts.FinalResponse(
        text="Total revenue in January 2026 was $2,050.00.",
        trust_summary=contracts.TrustSummary(datasets=("Retail Operations",)),
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
        _progress_sink: contracts.ProgressSink,
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
    assert record["dataset"] == "Retail Operations"
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
        _progress_sink: contracts.ProgressSink,
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


def test_on_user_message_logs_provider_failure_diagnostic_context(
    tmp_path: pathlib.Path,
    connect_orders: collections.abc.Callable[
        ..., contextlib.AbstractContextManager[duckdb.DuckDBPyConnection]
    ],
) -> None:
    log_path = tmp_path / "interactions.jsonl"
    non_answer = contracts.NonAnswer(
        stage=contracts.NonAnswerStage.QUESTION_INTERPRETER,
        reason_code=contracts.NonAnswerReasonCode.PROVIDER_FAILURE,
        context=("structured_output_retry_exhausted",),
    )
    final = contracts.FinalResponse(
        text="I cannot answer safely yet because the provider could not respond.",
        trust_summary=contracts.TrustSummary(),
        response_kind=contracts.ResponseKind.UNSUPPORTED,
        non_answer=non_answer,
    )

    def answer_path(
        _connection: duckdb.DuckDBPyConnection,
        _question: str,
        _identity: contracts.InternalIdentity,
        _progress_sink: contracts.ProgressSink,
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
    assert record["reason_code"] == "provider_failure"
    assert record["stage"] == "question_interpreter"
    assert record["context"] == ["structured_output_retry_exhausted"]
    assert record["response_text"] == (
        "I cannot answer safely yet because the provider could not respond."
    )


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
        _progress_sink: contracts.ProgressSink,
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

    # The user still gets the Runtime Fallback reply (now with flag buttons).
    assert len(say.calls) == 1
    assert say.calls[0][0] == slack_assistant.RUNTIME_FALLBACK_MESSAGE
    records = _read_log_records(log_path)
    assert len(records) == 1
    record = records[0]
    assert record["outcome"] == "error"
    assert record["error_type"] == "RuntimeError"
    assert record["error_message"] == "answer path blew up"
    assert record["flags"] == []


def test_record_runtime_error_logs_qa_review_metadata(
    tmp_path: pathlib.Path,
    connect_orders: collections.abc.Callable[
        ..., contextlib.AbstractContextManager[duckdb.DuckDBPyConnection]
    ],
) -> None:
    log_path = tmp_path / "interactions.jsonl"

    def answer_path(
        _connection: duckdb.DuckDBPyConnection,
        _question: str,
        _identity: contracts.InternalIdentity,
        _progress_sink: contracts.ProgressSink,
    ) -> slack_assistant.SlackWorkflowResult:
        return _final_response()

    adapter = slack_assistant.AssistantAdapter(
        connection_factory=_connection_factory(connect_orders),
        answer_path=answer_path,
        log_path=log_path,
    )

    adapter.record_runtime_error(
        question="What failed?",
        user="qa_driver",
        error=RuntimeError("answer path blew up"),
        qa_review_context=interaction_record.QAReviewContext(
            battery_path="docs/qa-retail-questions.md",
            qa_case_id="case-a",
            known_issues=(
                known_qa_issues.KnownQAIssue(
                    issue_number=166,
                    flag_category="correctness",
                ),
            ),
        ),
    )

    records = _read_log_records(log_path)
    assert len(records) == 1
    assert records[0]["outcome"] == "error"
    assert records[0]["source"] == "qa_review"
    assert records[0]["battery_path"] == "docs/qa-retail-questions.md"
    assert records[0]["qa_case_id"] == "case-a"
    assert records[0]["known_issues"] == [
        {"issue_number": 166, "flag_category": "correctness"}
    ]


def test_answer_and_render_returns_id_response_blocks_and_logs_one_record(
    tmp_path: pathlib.Path,
    connect_orders: collections.abc.Callable[
        ..., contextlib.AbstractContextManager[duckdb.DuckDBPyConnection]
    ],
) -> None:
    """The extracted success core: id -> answer -> log -> render-with-buttons.

    Both ``on_user_message`` and the Slack QA driver call this, so it must return
    everything a caller needs to post the reply AND append exactly one record.
    """
    log_path = tmp_path / "interactions.jsonl"
    set_status = RecordingStatus()
    seen_questions: list[str] = []
    blocks: tuple[contracts.SlackBlock, ...] = (
        {"type": "section", "text": {"type": "mrkdwn", "text": "trust"}},
    )

    def answer_path(
        _connection: duckdb.DuckDBPyConnection,
        question: str,
        _identity: contracts.InternalIdentity,
        progress_sink: contracts.ProgressSink,
    ) -> slack_assistant.SlackWorkflowResult:
        progress_sink(EXPECTED_PROGRESS_STATUSES[0])
        seen_questions.append(question)
        return _final_response(text="Final answer text.", blocks=blocks)

    adapter = slack_assistant.AssistantAdapter(
        connection_factory=_connection_factory(connect_orders),
        answer_path=answer_path,
        model_label="gpt-4o-mini",
        log_path=log_path,
    )

    interaction_id, final_response, reply_blocks = adapter.answer_and_render(
        text="What was total revenue by region in January 2026?",
        user="U123",
        set_status=set_status,
    )

    # Progress flows through the injected status sink.
    assert set_status.calls == [EXPECTED_PROGRESS_STATUSES[0]]
    assert seen_questions == ["What was total revenue by region in January 2026?"]
    # The triple lets the driver post the reply as the bot.
    assert isinstance(interaction_id, str) and interaction_id
    assert final_response.text == "Final answer text."
    reply_blocks = tuple(reply_blocks)
    # Every reply leads with a context echo of the original question.
    assert reply_blocks[0]["type"] == "context"
    assert (
        _context_text(reply_blocks[0])
        == "❓ What was total revenue by region in January 2026?"
    )
    assert reply_blocks[1 : 1 + len(blocks)] == blocks
    assert _action_ids_in(reply_blocks) == {
        slack_assistant.FLAG_CORRECTNESS_ACTION_ID,
        slack_assistant.FLAG_FORMATTING_ACTION_ID,
        slack_assistant.FLAG_INVESTIGATE_ACTION_ID,
    }
    # The flag buttons carry the SAME id that was returned, so a clicked flag
    # attaches to the record this call appended.
    for block in reply_blocks:
        if block.get("type") != "actions":
            continue
        for element in _button_elements(block):
            assert element["value"] == interaction_id

    # Exactly one record was appended, under the returned id.
    records = _read_log_records(log_path)
    assert len(records) == 1
    assert records[0]["id"] == interaction_id
    # A bare FinalResponse records as a non_answer (ADR-0016 result branching);
    # the point here is the single record under the returned id, not its outcome.
    assert records[0]["outcome"] == "non_answer"
    assert records[0]["model"] == "gpt-4o-mini"
    assert records[0]["user"] == "U123"
    assert "qa_case_id" not in records[0]


def test_answer_and_render_logs_optional_qa_case_id_without_changing_question(
    tmp_path: pathlib.Path,
    connect_orders: collections.abc.Callable[
        ..., contextlib.AbstractContextManager[duckdb.DuckDBPyConnection]
    ],
) -> None:
    log_path = tmp_path / "interactions.jsonl"

    def answer_path(
        _connection: duckdb.DuckDBPyConnection,
        _question: str,
        _identity: contracts.InternalIdentity,
        _progress_sink: contracts.ProgressSink,
    ) -> slack_assistant.SlackWorkflowResult:
        return _final_response(text="Final answer text.")

    adapter = slack_assistant.AssistantAdapter(
        connection_factory=_connection_factory(connect_orders),
        answer_path=answer_path,
        log_path=log_path,
    )

    interaction_id, _final_response_out, _reply_blocks = adapter.answer_and_render(
        text="What was total revenue by region in January 2026?",
        user="qa_driver",
        qa_case_id="orders-net-revenue-by-store-region-q1-2026",
        set_status=RecordingStatus(),
    )

    records = _read_log_records(log_path)
    assert len(records) == 1
    assert records[0]["id"] == interaction_id
    assert records[0]["question"] == "What was total revenue by region in January 2026?"
    assert records[0]["qa_case_id"] == "orders-net-revenue-by-store-region-q1-2026"


def test_answer_and_render_logs_qa_review_metadata(
    tmp_path: pathlib.Path,
    connect_orders: collections.abc.Callable[
        ..., contextlib.AbstractContextManager[duckdb.DuckDBPyConnection]
    ],
) -> None:
    log_path = tmp_path / "interactions.jsonl"

    def answer_path(
        _connection: duckdb.DuckDBPyConnection,
        _question: str,
        _identity: contracts.InternalIdentity,
        _progress_sink: contracts.ProgressSink,
    ) -> slack_assistant.SlackWorkflowResult:
        return _final_response(text="Final answer text.")

    adapter = slack_assistant.AssistantAdapter(
        connection_factory=_connection_factory(connect_orders),
        answer_path=answer_path,
        log_path=log_path,
    )

    adapter.answer_and_render(
        text="What was total revenue by region in January 2026?",
        user="qa_driver",
        set_status=RecordingStatus(),
        qa_review_context=interaction_record.QAReviewContext(
            battery_path="docs/qa-retail-questions.md",
            qa_case_id="orders-net-revenue-by-store-region-q1-2026",
            known_issues=(
                known_qa_issues.KnownQAIssue(
                    issue_number=166,
                    flag_category="correctness",
                ),
            ),
        ),
    )

    records = _read_log_records(log_path)
    assert len(records) == 1
    assert records[0]["source"] == "qa_review"
    assert records[0]["battery_path"] == "docs/qa-retail-questions.md"
    assert records[0]["qa_case_id"] == "orders-net-revenue-by-store-region-q1-2026"
    assert records[0]["known_issues"] == [
        {"issue_number": 166, "flag_category": "correctness"}
    ]


def test_answer_and_render_omits_known_issue_metadata_for_unidentified_qa_case(
    tmp_path: pathlib.Path,
    connect_orders: collections.abc.Callable[
        ..., contextlib.AbstractContextManager[duckdb.DuckDBPyConnection]
    ],
) -> None:
    log_path = tmp_path / "interactions.jsonl"

    def answer_path(
        _connection: duckdb.DuckDBPyConnection,
        _question: str,
        _identity: contracts.InternalIdentity,
        _progress_sink: contracts.ProgressSink,
    ) -> slack_assistant.SlackWorkflowResult:
        return _final_response(text="Final answer text.")

    adapter = slack_assistant.AssistantAdapter(
        connection_factory=_connection_factory(connect_orders),
        answer_path=answer_path,
        log_path=log_path,
    )

    adapter.answer_and_render(
        text="Legacy question?",
        user="qa_driver",
        set_status=RecordingStatus(),
        qa_review_context=interaction_record.QAReviewContext(
            battery_path="docs/qa-retail-questions.md",
            qa_case_id=None,
            known_issues=(),
        ),
    )

    records = _read_log_records(log_path)
    assert len(records) == 1
    assert records[0]["source"] == "qa_review"
    assert records[0]["battery_path"] == "docs/qa-retail-questions.md"
    assert "qa_case_id" not in records[0]
    assert "known_issues" not in records[0]


def test_answer_and_render_logs_empty_known_issues_for_identified_qa_case(
    tmp_path: pathlib.Path,
    connect_orders: collections.abc.Callable[
        ..., contextlib.AbstractContextManager[duckdb.DuckDBPyConnection]
    ],
) -> None:
    log_path = tmp_path / "interactions.jsonl"

    def answer_path(
        _connection: duckdb.DuckDBPyConnection,
        _question: str,
        _identity: contracts.InternalIdentity,
        _progress_sink: contracts.ProgressSink,
    ) -> slack_assistant.SlackWorkflowResult:
        return _final_response(text="Final answer text.")

    adapter = slack_assistant.AssistantAdapter(
        connection_factory=_connection_factory(connect_orders),
        answer_path=answer_path,
        log_path=log_path,
    )

    adapter.answer_and_render(
        text="Question with no remaining known issues?",
        user="qa_driver",
        set_status=RecordingStatus(),
        qa_review_context=interaction_record.QAReviewContext(
            battery_path="docs/qa-retail-questions.md",
            qa_case_id="case-without-known-issues",
            known_issues=(),
        ),
    )

    records = _read_log_records(log_path)
    assert len(records) == 1
    assert records[0]["source"] == "qa_review"
    assert records[0]["battery_path"] == "docs/qa-retail-questions.md"
    assert records[0]["qa_case_id"] == "case-without-known-issues"
    assert records[0]["known_issues"] == []


def test_answer_and_render_keeps_normal_reply_without_qa_header_or_qa_buttons(
    tmp_path: pathlib.Path,
    connect_orders: collections.abc.Callable[
        ..., contextlib.AbstractContextManager[duckdb.DuckDBPyConnection]
    ],
) -> None:
    def answer_path(
        _connection: duckdb.DuckDBPyConnection,
        _question: str,
        _identity: contracts.InternalIdentity,
        _progress_sink: contracts.ProgressSink,
    ) -> slack_assistant.SlackWorkflowResult:
        return _final_response(
            text="Final answer text.",
            blocks=(
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": "trust"},
                },
            ),
        )

    adapter = slack_assistant.AssistantAdapter(
        connection_factory=_connection_factory(connect_orders),
        answer_path=answer_path,
        log_path=tmp_path / "interactions.jsonl",
    )

    interaction_id, _final_response_out, reply_blocks = adapter.answer_and_render(
        text="Normal question?",
        user="U123",
        set_status=RecordingStatus(),
    )

    assert _context_text(reply_blocks[0]) == "❓ Normal question?"
    assert len(_actions_blocks(reply_blocks)) == 1
    assert _action_ids_in(reply_blocks) == {
        slack_assistant.FLAG_CORRECTNESS_ACTION_ID,
        slack_assistant.FLAG_FORMATTING_ACTION_ID,
        slack_assistant.FLAG_INVESTIGATE_ACTION_ID,
    }
    for element in _button_elements(_actions_blocks(reply_blocks)[0]):
        assert element["value"] == interaction_id


def test_answer_and_render_adds_qa_header_and_combined_qa_actions(
    tmp_path: pathlib.Path,
    connect_orders: collections.abc.Callable[
        ..., contextlib.AbstractContextManager[duckdb.DuckDBPyConnection]
    ],
) -> None:
    answer_blocks: tuple[contracts.SlackBlock, ...] = (
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": "Answer body"},
        },
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": "Trust summary"},
        },
    )

    def answer_path(
        _connection: duckdb.DuckDBPyConnection,
        _question: str,
        _identity: contracts.InternalIdentity,
        _progress_sink: contracts.ProgressSink,
    ) -> slack_assistant.SlackWorkflowResult:
        return _final_response(text="Final answer text.", blocks=answer_blocks)

    adapter = slack_assistant.AssistantAdapter(
        connection_factory=_connection_factory(connect_orders),
        answer_path=answer_path,
        log_path=tmp_path / "interactions.jsonl",
    )

    interaction_id, _final_response_out, reply_blocks = adapter.answer_and_render(
        text="QA question?",
        user="qa_driver",
        set_status=RecordingStatus(),
        qa_review_context=interaction_record.QAReviewContext(
            battery_path="docs/qa-retail-questions.md",
            qa_case_id="case-a",
            known_issues=(
                known_qa_issues.KnownQAIssue(
                    issue_number=166,
                    flag_category="correctness",
                ),
                known_qa_issues.KnownQAIssue(
                    issue_number=169,
                    flag_category="formatting",
                ),
            ),
            position=1,
            total=3,
            note_saved=True,
        ),
    )

    assert _context_text(reply_blocks[0]).startswith("QA 1/3")
    assert "Case `case-a`" in _context_text(reply_blocks[0])
    assert "#166" in _context_text(reply_blocks[0])
    assert "🚩" in _context_text(reply_blocks[0])
    assert "#169" in _context_text(reply_blocks[0])
    assert "🎨" in _context_text(reply_blocks[0])
    assert "Note saved" in _context_text(reply_blocks[0])
    assert _context_text(reply_blocks[1]) == "❓ QA question?"
    assert reply_blocks[2:4] == answer_blocks
    assert len(_actions_blocks(reply_blocks)) == 1
    assert _action_ids_in(reply_blocks) == {
        slack_assistant.FLAG_CORRECTNESS_ACTION_ID,
        slack_assistant.FLAG_FORMATTING_ACTION_ID,
        slack_assistant.FLAG_INVESTIGATE_ACTION_ID,
        slack_assistant.QA_ADD_NOTE_ACTION_ID,
        slack_assistant.QA_DONE_ACTION_ID,
    }
    for element in _button_elements(_actions_blocks(reply_blocks)[0]):
        assert element["value"] == interaction_id


def test_answer_and_render_qa_header_omits_case_id_for_unidentified_case(
    tmp_path: pathlib.Path,
    connect_orders: collections.abc.Callable[
        ..., contextlib.AbstractContextManager[duckdb.DuckDBPyConnection]
    ],
) -> None:
    def answer_path(
        _connection: duckdb.DuckDBPyConnection,
        _question: str,
        _identity: contracts.InternalIdentity,
        _progress_sink: contracts.ProgressSink,
    ) -> slack_assistant.SlackWorkflowResult:
        return _final_response(text="Final answer text.")

    adapter = slack_assistant.AssistantAdapter(
        connection_factory=_connection_factory(connect_orders),
        answer_path=answer_path,
        log_path=tmp_path / "interactions.jsonl",
    )

    _interaction_id, _final_response_out, reply_blocks = adapter.answer_and_render(
        text="Legacy question?",
        user="qa_driver",
        set_status=RecordingStatus(),
        qa_review_context=interaction_record.QAReviewContext(
            battery_path="docs/qa-retail-questions.md",
            qa_case_id=None,
            known_issues=(),
            position=2,
            total=5,
        ),
    )

    assert _context_text(reply_blocks[0]).startswith("QA 2/5")
    assert "Case `" not in _context_text(reply_blocks[0])
    assert _context_text(reply_blocks[1]) == "❓ Legacy question?"


def test_answer_and_render_truncates_long_question_in_echo_block(
    tmp_path: pathlib.Path,
    connect_orders: collections.abc.Callable[
        ..., contextlib.AbstractContextManager[duckdb.DuckDBPyConnection]
    ],
) -> None:
    """The leading echo trims an over-cap question with a ``…`` suffix.

    The full question still lands in the Interaction Log ``question`` field, so
    the trim is cosmetic to the context line only.
    """
    long_question = "x" * (slack_assistant.QUESTION_ECHO_MAX_CHARS + 50)

    def answer_path(
        _connection: duckdb.DuckDBPyConnection,
        _question: str,
        _identity: contracts.InternalIdentity,
        _progress_sink: contracts.ProgressSink,
    ) -> slack_assistant.SlackWorkflowResult:
        return _final_response(text="Final answer text.")

    log_path = tmp_path / "interactions.jsonl"
    adapter = slack_assistant.AssistantAdapter(
        connection_factory=_connection_factory(connect_orders),
        answer_path=answer_path,
        log_path=log_path,
    )

    interaction_id, _final_response_out, reply_blocks = adapter.answer_and_render(
        text=long_question,
        user="U123",
        set_status=RecordingStatus(),
    )

    echo_text = _context_text(tuple(reply_blocks)[0])
    assert echo_text.startswith("❓ ")
    assert echo_text.endswith("…")
    body = echo_text[len("❓ ") :]
    assert len(body) == slack_assistant.QUESTION_ECHO_MAX_CHARS + 1  # cap + "…"
    # The untruncated question is still logged in full.
    records = _read_log_records(log_path)
    assert records[0]["id"] == interaction_id
    assert records[0]["question"] == long_question


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
        _progress_sink: contracts.ProgressSink,
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
    assert len(say.calls) == 1
    assert say.calls[0][0] == "Answer text."


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

    monkeypatch.setattr(interaction_record, "build_interaction_record", boom)

    def answer_path(
        _connection: duckdb.DuckDBPyConnection,
        _question: str,
        _identity: contracts.InternalIdentity,
        _progress_sink: contracts.ProgressSink,
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
    assert len(say.calls) == 1
    assert say.calls[0][0] == run.final_response.text
    assert say.calls[0][0] != slack_assistant.RUNTIME_FALLBACK_MESSAGE
    assert not log_path.exists()


# --- Flag buttons + block_actions core (issue #111) -------------------------


def test_flag_action_blocks_carries_interaction_id_and_action_ids() -> None:
    blocks = slack_assistant.flag_action_blocks("interaction-xyz")

    assert _action_ids_in(blocks) == {
        slack_assistant.FLAG_CORRECTNESS_ACTION_ID,
        slack_assistant.FLAG_FORMATTING_ACTION_ID,
        slack_assistant.FLAG_INVESTIGATE_ACTION_ID,
    }
    # Every button carries the interaction id in its ``value`` so the handler
    # can flag the right record.
    for block in blocks:
        if block.get("type") != "actions":
            continue
        for element in _button_elements(block):
            assert element["value"] == "interaction-xyz"


def test_action_id_to_category_is_single_source_of_truth() -> None:
    assert slack_assistant.ACTION_ID_TO_CATEGORY == {
        slack_assistant.FLAG_CORRECTNESS_ACTION_ID: "correctness",
        slack_assistant.FLAG_FORMATTING_ACTION_ID: "formatting",
        slack_assistant.FLAG_INVESTIGATE_ACTION_ID: "investigate",
    }
    # The mapped categories are exactly the Interaction Log flag vocabulary.
    assert set(slack_assistant.ACTION_ID_TO_CATEGORY.values()) == set(
        interaction_log.FLAG_VOCABULARY
    )


class _RecordingFlagStore:
    """Fake ``flag_interaction`` seam: records calls, returns a fixed result."""

    def __init__(self, *, result: bool = True) -> None:
        self.calls: list[tuple[str, str]] = []
        self._result = result

    def __call__(self, interaction_id: str, category: str) -> bool:
        self.calls.append((interaction_id, category))
        return self._result


class _RecordingDeleteMessage:
    """Fake ``chat_delete`` seam: records calls, optionally raises."""

    def __init__(self, *, error: BaseException | None = None) -> None:
        self.calls: list[tuple[str, str]] = []
        self._error = error

    def __call__(self, channel: str, ts: str) -> None:
        self.calls.append((channel, ts))
        if self._error is not None:
            raise self._error


class _RecordingNoteStore:
    def __init__(self, *, result: bool = True) -> None:
        self.calls: list[tuple[str, str]] = []
        self._result = result

    def __call__(self, interaction_id: str, note: str) -> bool:
        self.calls.append((interaction_id, note))
        return self._result


def _answer_blocks() -> list[dict[str, object]]:
    """A minimal Assistant reply: a section + the flag buttons."""
    return [
        {"type": "section", "text": {"type": "mrkdwn", "text": "the answer"}},
        *slack_assistant.flag_action_blocks("abc123"),
    ]


def _status_text(
    blocks: collections.abc.Sequence[contracts.SlackBlock],
) -> str | None:
    for block in blocks:
        if block.get("block_id") == slack_assistant.FLAG_STATUS_BLOCK_ID:
            elements = block["elements"]
            assert isinstance(elements, list)
            first = typing.cast("list[dict[str, object]]", elements)[0]
            return str(first["text"])
    return None


def _qa_done_body(
    *,
    channel_id: object = "C123",
    container_message_ts: object = "1748880000.123456",
    message_ts: object = "1748880000.123456",
    value: object = "interaction-123",
) -> dict[str, object]:
    return {
        "channel": {"id": channel_id},
        "container": {"message_ts": container_message_ts},
        "message": {
            "ts": message_ts,
            "blocks": list(slack_assistant.qa_action_blocks("interaction-123")),
        },
        "actions": [
            {
                "action_id": slack_assistant.QA_DONE_ACTION_ID,
                "value": value,
            }
        ],
    }


def _qa_note_view_state(note: str) -> dict[str, object]:
    return {
        "values": {
            slack_assistant.QA_REVIEW_NOTE_BLOCK_ID: {
                slack_assistant.QA_REVIEW_NOTE_ACTION_ID: {
                    "type": "plain_text_input",
                    "value": note,
                }
            }
        }
    }


def test_apply_flag_appends_status_line_and_keeps_answer_and_buttons() -> None:
    store = _RecordingFlagStore()
    original = _answer_blocks()

    new_blocks = slack_assistant.apply_flag(
        action_id=slack_assistant.FLAG_CORRECTNESS_ACTION_ID,
        interaction_id="abc123",
        blocks=original,
        flag_store=store,
    )

    assert store.calls == [("abc123", "correctness")]
    assert new_blocks is not None
    # The answer body and the flag buttons survive (buttons stay clickable).
    assert new_blocks[0] == original[0]
    assert _action_ids_in(new_blocks) == {
        slack_assistant.FLAG_CORRECTNESS_ACTION_ID,
        slack_assistant.FLAG_FORMATTING_ACTION_ID,
        slack_assistant.FLAG_INVESTIGATE_ACTION_ID,
    }
    assert _status_text(new_blocks) == "✓ Flagged: correctness"


def test_apply_flag_second_category_merges_in_vocabulary_order() -> None:
    store = _RecordingFlagStore()
    after_first = slack_assistant.apply_flag(
        action_id=slack_assistant.FLAG_FORMATTING_ACTION_ID,
        interaction_id="abc123",
        blocks=_answer_blocks(),
        flag_store=store,
    )
    assert after_first is not None
    assert _status_text(after_first) == "✓ Flagged: formatting"

    after_second = slack_assistant.apply_flag(
        action_id=slack_assistant.FLAG_CORRECTNESS_ACTION_ID,
        interaction_id="abc123",
        blocks=after_first,
        flag_store=store,
    )

    assert after_second is not None
    # Merged, deduped, ordered by FLAG_VOCABULARY -- not stacked, not overwritten.
    assert _status_text(after_second) == "✓ Flagged: correctness, formatting"
    status_blocks = [
        b
        for b in after_second
        if b.get("block_id") == slack_assistant.FLAG_STATUS_BLOCK_ID
    ]
    assert len(status_blocks) == 1


def test_apply_flag_investigate_flags_and_renders_status() -> None:
    store = _RecordingFlagStore()
    original = _answer_blocks()

    new_blocks = slack_assistant.apply_flag(
        action_id=slack_assistant.FLAG_INVESTIGATE_ACTION_ID,
        interaction_id="abc123",
        blocks=original,
        flag_store=store,
    )

    assert store.calls == [("abc123", "investigate")]
    assert new_blocks is not None
    assert _status_text(new_blocks) == "✓ Flagged: investigate"


def test_apply_flag_correctness_plus_investigate_merges_in_vocab_order() -> None:
    store = _RecordingFlagStore()
    after_first = slack_assistant.apply_flag(
        action_id=slack_assistant.FLAG_INVESTIGATE_ACTION_ID,
        interaction_id="abc123",
        blocks=_answer_blocks(),
        flag_store=store,
    )
    assert after_first is not None

    after_second = slack_assistant.apply_flag(
        action_id=slack_assistant.FLAG_CORRECTNESS_ACTION_ID,
        interaction_id="abc123",
        blocks=after_first,
        flag_store=store,
    )

    assert after_second is not None
    # Ordered by FLAG_VOCABULARY: correctness precedes investigate.
    assert _status_text(after_second) == "✓ Flagged: correctness, investigate"


def test_apply_flag_duplicate_click_is_idempotent() -> None:
    store = _RecordingFlagStore()
    first = slack_assistant.apply_flag(
        action_id=slack_assistant.FLAG_CORRECTNESS_ACTION_ID,
        interaction_id="abc123",
        blocks=_answer_blocks(),
        flag_store=store,
    )
    assert first is not None
    second = slack_assistant.apply_flag(
        action_id=slack_assistant.FLAG_CORRECTNESS_ACTION_ID,
        interaction_id="abc123",
        blocks=first,
        flag_store=store,
    )

    assert second is not None
    assert _status_text(second) == "✓ Flagged: correctness"


def test_apply_flag_unknown_id_leaves_blocks_unchanged() -> None:
    store = _RecordingFlagStore(result=False)
    original = _answer_blocks()

    new_blocks = slack_assistant.apply_flag(
        action_id=slack_assistant.FLAG_CORRECTNESS_ACTION_ID,
        interaction_id="missing",
        blocks=original,
        flag_store=store,
    )

    # Store was consulted, but an unknown id adds no status line (benign no-op).
    assert store.calls == [("missing", "correctness")]
    assert new_blocks is not None
    assert _status_text(new_blocks) is None
    assert _action_ids_in(new_blocks) == {
        slack_assistant.FLAG_CORRECTNESS_ACTION_ID,
        slack_assistant.FLAG_FORMATTING_ACTION_ID,
        slack_assistant.FLAG_INVESTIGATE_ACTION_ID,
    }


def test_apply_flag_unknown_action_id_is_defensive_noop() -> None:
    store = _RecordingFlagStore()

    new_blocks = slack_assistant.apply_flag(
        action_id="not_a_flag_button",
        interaction_id="abc123",
        blocks=_answer_blocks(),
        flag_store=store,
    )

    # Defensive: an unmapped action_id never flags, returns None (nothing to do).
    assert store.calls == []
    assert new_blocks is None


def test_apply_qa_done_deletes_message_from_normal_payload() -> None:
    delete_message = _RecordingDeleteMessage()

    deleted = slack_assistant.apply_qa_done(
        body=_qa_done_body(),
        delete_message=delete_message,
    )

    assert deleted is True
    assert delete_message.calls == [("C123", "1748880000.123456")]


def test_apply_qa_done_ignores_missing_or_unrelated_button_value() -> None:
    delete_message = _RecordingDeleteMessage()

    deleted = slack_assistant.apply_qa_done(
        body=_qa_done_body(value=None),
        delete_message=delete_message,
    )

    assert deleted is True
    assert delete_message.calls == [("C123", "1748880000.123456")]


def test_apply_qa_done_falls_back_to_message_ts() -> None:
    delete_message = _RecordingDeleteMessage()

    deleted = slack_assistant.apply_qa_done(
        body=_qa_done_body(
            container_message_ts=None,
            message_ts="1748889999.000001",
        ),
        delete_message=delete_message,
    )

    assert deleted is True
    assert delete_message.calls == [("C123", "1748889999.000001")]


@pytest.mark.parametrize(
    ("channel_id", "container_message_ts", "message_ts"),
    [
        (None, "1748880000.123456", "1748880000.123456"),
        ("", "1748880000.123456", "1748880000.123456"),
        ("C123", None, None),
        ("C123", "", ""),
    ],
)
def test_apply_qa_done_safe_noop_for_malformed_payload(
    channel_id: object,
    container_message_ts: object,
    message_ts: object,
) -> None:
    delete_message = _RecordingDeleteMessage()

    deleted = slack_assistant.apply_qa_done(
        body=_qa_done_body(
            channel_id=channel_id,
            container_message_ts=container_message_ts,
            message_ts=message_ts,
        ),
        delete_message=delete_message,
    )

    assert deleted is False
    assert delete_message.calls == []


def test_apply_qa_done_catches_delete_failure_without_crashing() -> None:
    delete_message = _RecordingDeleteMessage(error=RuntimeError("Slack down"))

    deleted = slack_assistant.apply_qa_done(
        body=_qa_done_body(),
        delete_message=delete_message,
    )

    assert deleted is False
    assert delete_message.calls == [("C123", "1748880000.123456")]


def test_qa_action_blocks_include_done_but_flag_blocks_do_not() -> None:
    qa_action_ids = _action_ids_in(slack_assistant.qa_action_blocks("interaction-xyz"))
    flag_action_ids = _action_ids_in(
        slack_assistant.flag_action_blocks("interaction-xyz")
    )

    assert slack_assistant.QA_DONE_ACTION_ID in qa_action_ids
    assert slack_assistant.QA_DONE_ACTION_ID not in flag_action_ids
    assert slack_assistant.QA_ADD_NOTE_ACTION_ID in qa_action_ids
    assert slack_assistant.QA_ADD_NOTE_ACTION_ID not in flag_action_ids


def test_build_qa_review_note_modal_prefills_existing_note_and_metadata() -> None:
    view = slack_assistant.build_qa_review_note_modal(
        interaction_id="interaction-123",
        existing_note="Existing note",
        channel_id="C123",
        message_ts="1748880000.123456",
        message_text="QA answer text",
    )

    assert view["callback_id"] == slack_assistant.QA_REVIEW_NOTE_CALLBACK_ID
    assert view["private_metadata"]
    metadata = json.loads(str(view["private_metadata"]))
    assert metadata["interaction_id"] == "interaction-123"
    assert metadata["channel_id"] == "C123"
    assert metadata["message_ts"] == "1748880000.123456"
    assert metadata["message_text"] == "QA answer text"
    assert "original_blocks" not in metadata
    view_blocks = typing.cast("list[dict[str, object]]", view["blocks"])
    state = typing.cast("dict[str, object]", view_blocks[0]["element"])
    assert state["action_id"] == slack_assistant.QA_REVIEW_NOTE_ACTION_ID
    assert state["initial_value"] == "Existing note"


def test_apply_qa_review_note_save_persists_note_and_returns_small_update_target() -> (
    None
):
    note_store = _RecordingNoteStore()
    body = {
        "view": {
            "private_metadata": json.dumps(
                {
                    "interaction_id": "interaction-123",
                    "channel_id": "C123",
                    "message_ts": "1748880000.123456",
                    "message_text": "QA answer text",
                }
            ),
            "state": _qa_note_view_state("Saved note"),
        }
    }

    result = slack_assistant.apply_qa_review_note_save(
        body=body,
        note_store=note_store,
    )

    assert result is not None
    assert note_store.calls == [("interaction-123", "Saved note")]
    assert result["interaction_id"] == "interaction-123"
    assert result["channel_id"] == "C123"
    assert result["message_ts"] == "1748880000.123456"
    assert result["message_text"] == "QA answer text"


def test_render_note_saved_blocks_preserves_body_and_actions() -> None:
    original_blocks: list[contracts.SlackBlock] = [
        {
            "type": "context",
            "elements": [{"type": "mrkdwn", "text": "QA 1/3 • Case `case-a`"}],
        },
        {"type": "context", "elements": [{"type": "mrkdwn", "text": "❓ QA?"}]},
        {"type": "section", "text": {"type": "mrkdwn", "text": "Answer body"}},
        *slack_assistant.qa_action_blocks("interaction-123"),
    ]

    result_blocks = slack_assistant.render_note_saved_blocks(original_blocks)

    assert "Note saved" in _context_text(result_blocks[0])
    assert result_blocks[1:] == original_blocks[1:]


def test_apply_qa_review_note_save_unknown_id_returns_none() -> None:
    note_store = _RecordingNoteStore(result=False)
    body = {
        "view": {
            "private_metadata": json.dumps(
                {
                    "interaction_id": "missing",
                    "channel_id": "C123",
                    "message_ts": "1748880000.123456",
                }
            ),
            "state": _qa_note_view_state("Saved note"),
        }
    }

    result = slack_assistant.apply_qa_review_note_save(
        body=body,
        note_store=note_store,
    )

    assert result is None
    assert note_store.calls == [("missing", "Saved note")]


def test_flag_interaction_for_triage_logs_updated_record(
    caplog: pytest.LogCaptureFixture,
    tmp_path: pathlib.Path,
) -> None:
    log_path = tmp_path / "interactions.jsonl"
    record: dict[str, object] = {
        "id": "abc123",
        "timestamp": "2026-06-01T12:00:00+00:00",
        "user": "U123",
        "question": "What was revenue by region?",
        "latency_ms": 42,
        "outcome": "answer",
        "response_text": "answer",
        "model": "gpt-4o-mini",
        "flags": [],
    }
    interaction_log.append_interaction(record, path=log_path)

    with caplog.at_level(logging.WARNING, logger=slack_assistant.logger.name):
        changed = slack_assistant.flag_interaction_for_triage(
            interaction_id="abc123",
            category="correctness",
            log_path=log_path,
        )

    assert changed is True
    messages = [
        message
        for message in caplog.messages
        if message.startswith(slack_assistant.FLAGGED_INTERACTION_LOG_PREFIX)
    ]
    assert len(messages) == 1
    payload = messages[0][len(slack_assistant.FLAGGED_INTERACTION_LOG_PREFIX) :]
    mirrored_record = json.loads(payload)
    assert mirrored_record == {**record, "flags": ["correctness"]}


def test_flag_interaction_for_triage_unknown_id_logs_nothing(
    caplog: pytest.LogCaptureFixture,
    tmp_path: pathlib.Path,
) -> None:
    log_path = tmp_path / "interactions.jsonl"
    interaction_log.append_interaction(
        {
            "id": "abc123",
            "timestamp": "2026-06-01T12:00:00+00:00",
            "user": "U123",
            "question": "What was revenue by region?",
            "latency_ms": 42,
            "outcome": "answer",
            "response_text": "answer",
            "model": "gpt-4o-mini",
            "flags": [],
        },
        path=log_path,
    )

    with caplog.at_level(logging.WARNING, logger=slack_assistant.logger.name):
        changed = slack_assistant.flag_interaction_for_triage(
            interaction_id="missing",
            category="correctness",
            log_path=log_path,
        )

    assert changed is False
    assert not any(
        message.startswith(slack_assistant.FLAGGED_INTERACTION_LOG_PREFIX)
        for message in caplog.messages
    )

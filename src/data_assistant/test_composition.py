"""Tests for the shared startup composition helpers.

``composition`` owns the construction logic both Slack entrypoints share: the
OpenAI answer path builder, the DuckDB connection-factory builder, the env
resolvers (model label, Interaction Log path), the retail path constants, and
the single ``build_adapter`` adapter constructor. The Socket Mode startup and
the QA replay loop stay in their own modules and call these helpers.
"""

from __future__ import annotations

import collections.abc
import contextlib
import pathlib

import duckdb
import pytest

import data_assistant.composition as composition
import data_assistant.openai_support as openai_support
import data_assistant.slack_assistant as slack_assistant
import data_assistant.workflow.contracts as contracts


def _sentinel_answer_path(
    connection: duckdb.DuckDBPyConnection,
    question: str,
    internal_identity: contracts.InternalIdentity,
    progress_sink: contracts.ProgressSink,
) -> contracts.FinalResponse:
    del connection, question, internal_identity, progress_sink
    return contracts.FinalResponse(
        text="answer",
        trust_summary=contracts.TrustSummary(),
        response_kind=contracts.ResponseKind.ANSWER,
    )


def _connection_factory() -> contextlib.AbstractContextManager[
    duckdb.DuckDBPyConnection
]:
    raise AssertionError("connection factory should not run during construction")


def test_build_adapter_wires_caller_supplied_dependencies() -> None:
    """build_adapter forwards the caller's factory, answer path, and resolver."""
    resolver: slack_assistant.AssistantIdentityResolver = slack_assistant.dev_identity

    adapter = composition.build_adapter(
        connection_factory=_connection_factory,
        answer_path=_sentinel_answer_path,
        internal_identity_resolver=resolver,
        environ={},
    )

    assert adapter.connection_factory is _connection_factory
    assert adapter.answer_path is _sentinel_answer_path
    assert adapter.internal_identity_resolver is resolver


def test_build_adapter_resolves_default_model_label_from_environ() -> None:
    """With no OPENAI_MODEL override the default model label is recorded."""
    adapter = composition.build_adapter(
        connection_factory=_connection_factory,
        answer_path=_sentinel_answer_path,
        internal_identity_resolver=slack_assistant.default_identity,
        environ={},
    )

    assert adapter.model_label == openai_support.DEFAULT_OPENAI_MODEL


def test_build_adapter_threads_openai_model_override() -> None:
    """An OPENAI_MODEL override flows onto the adapter's model_label."""
    adapter = composition.build_adapter(
        connection_factory=_connection_factory,
        answer_path=_sentinel_answer_path,
        internal_identity_resolver=slack_assistant.default_identity,
        environ={"OPENAI_MODEL": "gpt-test-override"},
    )

    assert adapter.model_label == "gpt-test-override"


def test_build_adapter_resolves_default_log_path() -> None:
    """With no env var or override the adapter uses the default log path."""
    adapter = composition.build_adapter(
        connection_factory=_connection_factory,
        answer_path=_sentinel_answer_path,
        internal_identity_resolver=slack_assistant.default_identity,
        environ={},
    )

    assert adapter.log_path == composition.interaction_log.DEFAULT_LOG_PATH


def test_build_adapter_resolves_log_path_from_env_var(tmp_path: pathlib.Path) -> None:
    """The Interaction Log env var points the adapter at a persistent disk."""
    log_path = tmp_path / "render" / "interactions.jsonl"

    adapter = composition.build_adapter(
        connection_factory=_connection_factory,
        answer_path=_sentinel_answer_path,
        internal_identity_resolver=slack_assistant.default_identity,
        environ={composition.INTERACTION_LOG_PATH_ENV_VAR: str(log_path)},
    )

    assert adapter.log_path == log_path


def test_build_adapter_explicit_log_path_overrides_env(
    tmp_path: pathlib.Path,
) -> None:
    """An explicit log path wins over the env var (CLI override precedence)."""
    explicit = tmp_path / "explicit.jsonl"
    env_path = tmp_path / "env.jsonl"

    adapter = composition.build_adapter(
        connection_factory=_connection_factory,
        answer_path=_sentinel_answer_path,
        internal_identity_resolver=slack_assistant.default_identity,
        environ={composition.INTERACTION_LOG_PATH_ENV_VAR: str(env_path)},
        interaction_log_path=explicit,
    )

    assert adapter.log_path == explicit


def test_build_openai_answer_path_uses_openai_provider_without_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_providers: list[object] = []
    captured_reasoning_providers: list[object] = []

    class FakeProvider:
        pass

    class FakeReasoningProvider:
        pass

    def fake_build_openai_provider(
        environ: collections.abc.Mapping[str, str],
        *,
        client: object | None = None,
    ) -> FakeProvider:
        del client
        assert environ["OPENAI_API_KEY"] == "test-key"
        return FakeProvider()

    def fake_build_openai_reasoning_provider(
        environ: collections.abc.Mapping[str, str],
        *,
        client: object | None = None,
    ) -> FakeReasoningProvider:
        del client
        assert environ["OPENAI_API_KEY"] == "test-key"
        return FakeReasoningProvider()

    def fake_run_data_assistant(
        connection: duckdb.DuckDBPyConnection,
        question: str,
        internal_identity: contracts.InternalIdentity,
        progress_sink: contracts.ProgressSink,
        semantic_layer: object | None = None,
        question_interpreter_provider: object | None = None,
        reasoning_provider: object | None = None,
    ) -> contracts.FinalResponse:
        del connection, question, internal_identity, progress_sink, semantic_layer
        captured_providers.append(question_interpreter_provider)
        captured_reasoning_providers.append(reasoning_provider)
        return contracts.FinalResponse(
            text="openai answer path",
            trust_summary=contracts.TrustSummary(),
            response_kind=contracts.ResponseKind.ANSWER,
        )

    monkeypatch.setattr(
        composition.question_interpreter,
        "build_openai_question_interpreter_provider",
        fake_build_openai_provider,
    )
    monkeypatch.setattr(
        composition.reasoning_layer,
        "build_openai_reasoning_provider",
        fake_build_openai_reasoning_provider,
    )
    monkeypatch.setattr(
        composition.workflow_runner,
        "run_data_assistant",
        fake_run_data_assistant,
    )
    answer_path = composition.build_openai_answer_path({"OPENAI_API_KEY": "test-key"})

    with duckdb.connect(":memory:") as connection:
        result = answer_path(
            connection,
            "What was total revenue by region in January 2026?",
            contracts.InternalIdentity(identity_id="slack_user:U123"),
            lambda status: None,
        )

    assert isinstance(result, contracts.FinalResponse)
    assert result.response_kind == contracts.ResponseKind.ANSWER
    assert len(captured_providers) == 1
    assert isinstance(captured_providers[0], FakeProvider)
    assert len(captured_reasoning_providers) == 1
    assert isinstance(captured_reasoning_providers[0], FakeReasoningProvider)


def test_build_duckdb_connection_factory_runs_seed_sql(
    tmp_path: pathlib.Path,
) -> None:
    seed_sql_path = tmp_path / "seed.sql"
    seed_sql_path.write_text(
        "create table demo_value (value integer); insert into demo_value values (42);",
        encoding="utf-8",
    )
    connection_factory = composition.build_duckdb_connection_factory(
        ":memory:",
        seed_sql_path=seed_sql_path,
    )

    with connection_factory() as connection:
        row = connection.execute("select value from demo_value").fetchone()

    assert row == (42,)


def test_resolve_model_label_defaults_and_overrides() -> None:
    assert composition.resolve_model_label({}) == openai_support.DEFAULT_OPENAI_MODEL
    assert composition.resolve_model_label({"OPENAI_MODEL": "gpt-x"}) == "gpt-x"


def test_resolve_interaction_log_path_precedence(tmp_path: pathlib.Path) -> None:
    explicit = tmp_path / "explicit.jsonl"
    env_path = tmp_path / "env.jsonl"
    assert (
        composition.resolve_interaction_log_path({}, explicit_path=explicit) is explicit
    )
    assert (
        composition.resolve_interaction_log_path(
            {composition.INTERACTION_LOG_PATH_ENV_VAR: str(env_path)}
        )
        == env_path
    )
    assert (
        composition.resolve_interaction_log_path({})
        == composition.interaction_log.DEFAULT_LOG_PATH
    )


def test_retail_path_constants_exposed() -> None:
    """The retail app-run constants are the single source of truth here."""
    assert composition.RETAIL_DUCKDB_PATH == ":memory:"
    assert isinstance(composition.RETAIL_SEMANTIC_LAYER_PATH, pathlib.Path)
    assert isinstance(composition.RETAIL_SEED_SQL_PATH, pathlib.Path)


def test_connection_factory_type_alias_matches_slack_assistant() -> None:
    factory: composition.ConnectionFactory = _connection_factory
    typed: slack_assistant.ConnectionFactory = factory
    assert typed is _connection_factory

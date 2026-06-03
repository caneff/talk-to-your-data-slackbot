"""Shared startup composition for the Slack entrypoints.

Both Slack entrypoints -- the Socket Mode runtime (``slack_runtime``) and the
manual QA driver (``slack_qa_driver``) -- construct the same runtime objects:
the OpenAI-backed answer path, a DuckDB connection factory, the env-derived
model label + Interaction Log path, and the ``AssistantAdapter`` itself. This
module owns that construction so there is exactly one source of truth; the
entrypoints keep only their own startup shape (Socket Mode vs replay loop).

Flat layout for now -- this moves into ``slack/`` in a later issue (I5).
"""

from __future__ import annotations

import collections.abc as collections_abc
import contextlib
import pathlib
import typing

import duckdb

import data_assistant.interaction_log as interaction_log
import data_assistant.openai_support as openai_support
import data_assistant.question_interpreter as question_interpreter
import data_assistant.reasoning_layer as reasoning_layer
import data_assistant.semantic_layer.catalog as semantic_layer_catalog
import data_assistant.slack as slack_assistant
import data_assistant.workflow.contracts as contracts
import data_assistant.workflow.runner as workflow_runner

INTERACTION_LOG_PATH_ENV_VAR: typing.Final[str] = "DATA_ASSISTANT_INTERACTION_LOG_PATH"

# App-run defaults (one source of truth shared by both Slack entrypoints). A
# no-flag app run loads the retail layer + retail seed in :memory: (ADR-0001).
# Retail is now the single dataset, so the loader's DEFAULT_SEMANTIC_LAYER_PATH
# points at the same retail layer; these constants just pin the seed + :memory:
# app run.
RETAIL_SEMANTIC_LAYER_PATH: typing.Final[pathlib.Path] = pathlib.Path(
    "examples/retail_ops_demo/semantic_layer"
)
RETAIL_SEED_SQL_PATH: typing.Final[pathlib.Path] = pathlib.Path(
    "examples/retail_ops_demo/seeds/retail_ops_seed.sql"
)
RETAIL_DUCKDB_PATH: typing.Final[str] = ":memory:"

ConnectionFactory: typing.TypeAlias = slack_assistant.ConnectionFactory


def build_openai_answer_path(
    environ: collections_abc.Mapping[str, str],
    *,
    semantic_layer: semantic_layer_catalog.SemanticLayerCatalog | None = None,
) -> slack_assistant.AnswerPath:
    """Build the Slack answer path using the live OpenAI Question Interpreter."""
    provider = question_interpreter.build_openai_question_interpreter_provider(environ)
    reasoning_provider = reasoning_layer.build_openai_reasoning_provider(environ)

    def answer_path(
        connection: duckdb.DuckDBPyConnection,
        question: str,
        internal_identity: contracts.InternalIdentity,
        progress_sink: contracts.ProgressSink,
    ) -> slack_assistant.SlackWorkflowResult:
        return workflow_runner.run_data_assistant(
            connection,
            question,
            question_interpreter_provider=provider,
            reasoning_provider=reasoning_provider,
            internal_identity=internal_identity,
            semantic_layer=semantic_layer,
            progress_sink=progress_sink,
        )

    return answer_path


def resolve_model_label(environ: collections_abc.Mapping[str, str]) -> str:
    """Resolve the OpenAI model label recorded on each Interaction Log line.

    Sources the same ``OPENAI_MODEL`` env var (defaulting to
    ``openai_support.DEFAULT_OPENAI_MODEL``) that the live Question Interpreter
    provider uses, so the logged model matches the model actually invoked. Kept
    as a plain string rather than a live client to keep the adapter
    test-constructible without OpenAI configuration.
    """
    return environ.get("OPENAI_MODEL", openai_support.DEFAULT_OPENAI_MODEL)


def resolve_interaction_log_path(
    environ: collections_abc.Mapping[str, str],
    *,
    explicit_path: pathlib.Path | None = None,
) -> pathlib.Path:
    """Resolve the Interaction Log path for local, Docker, and Render runs."""
    if explicit_path is not None:
        return explicit_path
    configured_path = environ.get(INTERACTION_LOG_PATH_ENV_VAR)
    if configured_path:
        return pathlib.Path(configured_path)
    return interaction_log.DEFAULT_LOG_PATH


def build_duckdb_connection_factory(
    duckdb_path: str | pathlib.Path,
    *,
    seed_sql_path: str | pathlib.Path | None = None,
) -> ConnectionFactory:
    """Build a runtime connection factory for a configured DuckDB database."""
    duckdb_location = str(duckdb_path)
    seed_sql = (
        pathlib.Path(seed_sql_path).read_text(encoding="utf-8")
        if seed_sql_path is not None
        else None
    )

    @contextlib.contextmanager
    def connect() -> collections_abc.Generator[duckdb.DuckDBPyConnection]:
        connection = duckdb.connect(duckdb_location)
        try:
            if seed_sql is not None:
                connection.execute(seed_sql)
            yield connection
        finally:
            connection.close()

    return connect


def build_adapter(
    *,
    connection_factory: slack_assistant.ConnectionFactory,
    answer_path: slack_assistant.AnswerPath,
    internal_identity_resolver: slack_assistant.AssistantIdentityResolver,
    environ: collections_abc.Mapping[str, str],
    interaction_log_path: pathlib.Path | None = None,
) -> slack_assistant.AssistantAdapter:
    """Construct the shared AssistantAdapter both Slack entrypoints use.

    Resolves the model label and Interaction Log path from the environment
    internally so each entrypoint stops repeating that wiring. The answer path
    stays caller-built: the runtime passes a bare answer path while the driver
    binds a semantic layer first, so semantic-layer binding deliberately stays
    out of this constructor.
    """
    return slack_assistant.AssistantAdapter(
        connection_factory=connection_factory,
        answer_path=answer_path,
        internal_identity_resolver=internal_identity_resolver,
        model_label=resolve_model_label(environ),
        log_path=resolve_interaction_log_path(
            environ, explicit_path=interaction_log_path
        ),
    )

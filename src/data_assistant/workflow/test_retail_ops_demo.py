from __future__ import annotations

import contextlib
import pathlib
from collections.abc import Generator

import duckdb

import data_assistant.question_interpreter as question_interpreter
import data_assistant.semantic_layer.loader as semantic_layer_loader
import data_assistant.semantic_layer.schema as schema
import data_assistant.workflow.contracts as contracts
import data_assistant.workflow.runner as workflow_runner


def test_retail_ops_demo_questions_artifact_locks_runtime_and_demo_beats() -> None:
    artifact = pathlib.Path("examples/retail_ops_demo/demo_questions.md")

    assert artifact.exists()

    content = artifact.read_text(encoding="utf-8")

    assert (
        "uv run python -m data_assistant.slack_runtime "
        "--semantic-layer-path examples/retail_ops_demo/semantic_layer "
        "--duckdb-path :memory: "
        "--seed-sql-path examples/retail_ops_demo/seeds/retail_ops_seed.sql"
    ) in content
    assert "Assistant Suggested Prompt Set" in content
    assert "Use these exact prompts for Assistant suggested prompts:" in content
    assert "`What was total net revenue by store region in Q1 2026?`" in content
    assert "`What was total net revenue by store region?`" in content
    assert "`Which region had the highest total net revenue in Q1 2026?`" in content
    assert "Grounded answer with Trust Summary" in content
    assert "Refusal for unspecified Time Scope" in content
    assert "Won't-fabricate / visible degradation beat" in content


def test_retail_ops_demo_readme_links_locked_demo_questions() -> None:
    readme = pathlib.Path("examples/retail_ops_demo/README.md").read_text(
        encoding="utf-8"
    )

    assert "demo_questions.md" in readme


def test_retail_ops_demo_revenue_question_runs_end_to_end() -> None:
    proposal = question_interpreter.QuestionFrameProposal(
        intent="summarize",
        metric="total net revenue",
        field_operations=(
            question_interpreter.GroupByOperationProposal(
                operation="group_by",
                field="store region",
            ),
            question_interpreter.RangeFilterOperationProposal(
                operation="range_filter",
                field="order date",
                lower="2026-01-01",
                upper="2026-03-31",
            ),
        ),
    )

    with _connect_seeded_retail_ops() as connection:
        result = workflow_runner.run_data_assistant(
            connection,
            "What was total net revenue by store region in Q1 2026?",
            question_interpreter_provider=_static_provider(proposal),
            internal_identity=contracts.InternalIdentity(
                identity_id="local_development_user"
            ),
            semantic_layer=_retail_semantic_layer(),
        )

    assert isinstance(result, contracts.DataAssistantRun)
    assert result.available_data_resolution.resolved_match.table.table_id == (
        "demo_orders"
    )
    assert result.data_request.metric.label == "total net revenue"
    assert result.final_response.response_kind == contracts.ResponseKind.ANSWER
    assert "$486,277.25" in result.final_response.text
    assert "Trust Summary:" in result.final_response.text


def test_retail_ops_demo_gross_margin_question_runs_end_to_end() -> None:
    proposal = question_interpreter.QuestionFrameProposal(
        intent="summarize",
        metric="gross margin",
        field_operations=(
            question_interpreter.GroupByOperationProposal(
                operation="group_by",
                field="product category",
            ),
            question_interpreter.RangeFilterOperationProposal(
                operation="range_filter",
                field="order date",
                lower="2026-03-01",
                upper="2026-03-31",
            ),
        ),
    )

    with _connect_seeded_retail_ops() as connection:
        result = workflow_runner.run_data_assistant(
            connection,
            "What was gross margin by product category in March 2026?",
            question_interpreter_provider=_static_provider(proposal),
            internal_identity=contracts.InternalIdentity(
                identity_id="local_development_user"
            ),
            semantic_layer=_retail_semantic_layer(),
        )

    assert isinstance(result, contracts.DataAssistantRun)
    assert (
        result.available_data_resolution.resolved_match.table.table_id
        == "demo_order_lines"
    )
    assert result.data_request.metric.label == "gross margin"
    assert result.final_response.response_kind == contracts.ResponseKind.ANSWER
    assert "$112,882.65" in result.final_response.text
    assert "Trust Summary:" in result.final_response.text


def test_retail_ops_demo_support_tickets_question_runs_end_to_end() -> None:
    proposal = question_interpreter.QuestionFrameProposal(
        intent="summarize",
        metric="support ticket count",
        field_operations=(
            question_interpreter.GroupByOperationProposal(
                operation="group_by",
                field="issue category",
            ),
            question_interpreter.RangeFilterOperationProposal(
                operation="range_filter",
                field="ticket created date",
                lower="2026-04-01",
                upper="2026-04-30",
            ),
        ),
    )

    with _connect_seeded_retail_ops() as connection:
        result = workflow_runner.run_data_assistant(
            connection,
            "What was support ticket count by issue category in April 2026?",
            question_interpreter_provider=_static_provider(proposal),
            internal_identity=contracts.InternalIdentity(
                identity_id="local_development_user"
            ),
            semantic_layer=_retail_semantic_layer(),
        )

    assert isinstance(result, contracts.DataAssistantRun)
    assert (
        result.available_data_resolution.resolved_match.table.table_id
        == "demo_support_tickets"
    )
    assert result.data_request.metric.label == "support ticket count"
    assert result.final_response.response_kind == contracts.ResponseKind.ANSWER
    assert "Support ticket count in 2026-04-01 through 2026-04-30 was 90" in (
        result.final_response.text
    )
    assert "Trust Summary:" in result.final_response.text


def test_retail_ops_demo_missing_time_scope_returns_clarification() -> None:
    proposal = question_interpreter.QuestionFrameProposal(
        intent="summarize",
        metric="total net revenue",
        field_operations=(
            question_interpreter.GroupByOperationProposal(
                operation="group_by",
                field="store region",
            ),
        ),
    )

    with _connect_seeded_retail_ops() as connection:
        result = workflow_runner.run_data_assistant(
            connection,
            "What was total net revenue by store region?",
            question_interpreter_provider=_static_provider(proposal),
            internal_identity=contracts.InternalIdentity(
                identity_id="local_development_user"
            ),
            semantic_layer=_retail_semantic_layer(),
        )

    assert isinstance(result, contracts.FinalResponse)
    assert not isinstance(result, contracts.DataAssistantRun)
    assert result.response_kind == contracts.ResponseKind.CLARIFICATION_NEEDED
    assert "specify a time period or explicitly ask for all time" in result.text


def test_retail_ops_demo_rank_question_refuses_without_calling_provider() -> None:
    class ProviderThatMustNotBeCalled:
        def propose_question_frame(
            self,
            *,
            question: str,
            semantic_layer_context: dict[str, object],
        ) -> question_interpreter.QuestionFrameProposal:
            del question, semantic_layer_context
            raise AssertionError("rank intent guard should short-circuit provider")

    with _connect_seeded_retail_ops() as connection:
        result = workflow_runner.run_data_assistant(
            connection,
            "Which region had the highest total net revenue in Q1 2026?",
            question_interpreter_provider=ProviderThatMustNotBeCalled(),
            internal_identity=contracts.InternalIdentity(
                identity_id="local_development_user"
            ),
            semantic_layer=_retail_semantic_layer(),
        )

    assert isinstance(result, contracts.FinalResponse)
    assert not isinstance(result, contracts.DataAssistantRun)
    assert result.response_kind == contracts.ResponseKind.UNSUPPORTED
    assert "does not support that Data Question intent yet" in result.text


@contextlib.contextmanager
def _connect_seeded_retail_ops() -> Generator[duckdb.DuckDBPyConnection, None, None]:
    connection = duckdb.connect(":memory:")
    try:
        connection.execute(
            pathlib.Path(
                "examples/retail_ops_demo/seeds/retail_ops_seed.sql"
            ).read_text(encoding="utf-8")
        )
        yield connection
    finally:
        connection.close()


def _retail_semantic_layer() -> schema.SemanticLayer:
    return semantic_layer_loader.load_semantic_layer(
        pathlib.Path("examples/retail_ops_demo/semantic_layer")
    )


def _static_provider(
    proposal: question_interpreter.QuestionFrameProposal,
) -> question_interpreter.QuestionInterpreterProvider:
    class StaticProvider:
        def propose_question_frame(
            self,
            *,
            question: str,
            semantic_layer_context: dict[str, object],
        ) -> question_interpreter.QuestionFrameProposal:
            del question, semantic_layer_context
            return proposal

    return StaticProvider()

"""Tests for the Interaction Log record serializer (ADR-0016).

These exercise the contract-aware ``build_interaction_record`` /
``build_error_record`` mapping directly against fabricated workflow traces --
no Slack edge, no adapter, no file I/O. The end-to-end "the adapter appends one
sanitized line" behavior stays in ``test_slack_assistant.py``; here we pin the
record SHAPE (and its sanitization) at the unit boundary that owns it.
"""

from __future__ import annotations

import datetime
import json

import pandas as pd

import data_assistant.interaction_record as interaction_record
import data_assistant.known_qa_issues as known_qa_issues
import data_assistant.semantic_layer.schema as schema
import data_assistant.workflow.contracts as contracts


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


def _final_response(*, text: str) -> contracts.FinalResponse:
    return contracts.FinalResponse(
        text=text,
        trust_summary=contracts.TrustSummary(),
        response_kind=contracts.ResponseKind.ANSWER,
    )


def test_final_response_from_workflow_result_unwraps_run() -> None:
    final = _final_response(text="unwrapped")
    run = _data_assistant_run()

    # A bare FinalResponse passes through unchanged.
    assert interaction_record.final_response_from_workflow_result(final) is final
    # A DataAssistantRun yields its embedded final_response.
    assert (
        interaction_record.final_response_from_workflow_result(run)
        is run.final_response
    )


def test_build_interaction_record_answer_carries_shape_and_key_data() -> None:
    run = _data_assistant_run()

    record = interaction_record.build_interaction_record(
        interaction_id="abc123",
        timestamp="2026-01-01T00:00:00+00:00",
        latency_ms=42,
        user="U123",
        question="What was total revenue by region in January 2026?",
        qa_case_id=None,
        qa_review_context=None,
        model="gpt-4o-mini",
        result=run,
    )

    assert record["id"] == "abc123"
    assert record["outcome"] == "answer"
    assert record["model"] == "gpt-4o-mini"
    assert record["user"] == "U123"
    assert record["latency_ms"] == 42
    assert record["flags"] == []
    assert record["intent"] == "summarize"
    assert record["dataset"] == "Retail Operations"
    assert record["metric"] == "total revenue"
    assert record["metric_expression"] == "SUM(net_revenue)"
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
    serialized = json.dumps(record)
    assert "Acme-Secret-Corp" not in serialized
    assert "99999" not in serialized


def test_build_interaction_record_non_answer_carries_reason_and_stage() -> None:
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

    record = interaction_record.build_interaction_record(
        interaction_id="def456",
        timestamp="2026-01-01T00:00:00+00:00",
        latency_ms=7,
        user="U123",
        question="how much?",
        qa_case_id=None,
        qa_review_context=None,
        model="gpt-4o-mini",
        result=final,
    )

    assert record["outcome"] == "non_answer"
    assert record["reason_code"] == "missing_time_scope"
    assert record["stage"] == "question_interpreter"
    assert record["context"] == ["order date"]
    assert record["response_text"] == "I cannot answer safely yet because ..."
    assert record["flags"] == []


def test_build_interaction_record_includes_optional_qa_case_id() -> None:
    run = _data_assistant_run()

    record = interaction_record.build_interaction_record(
        interaction_id="abc123",
        timestamp="2026-01-01T00:00:00+00:00",
        latency_ms=1,
        user="U123",
        question="q",
        qa_case_id="case-7",
        qa_review_context=None,
        model="m",
        result=run,
    )

    assert record["qa_case_id"] == "case-7"


def test_build_error_record_carries_fallback_text_and_error_detail() -> None:
    record = interaction_record.build_error_record(
        interaction_id="err789",
        timestamp="2026-01-01T00:00:00+00:00",
        latency_ms=3,
        user="U123",
        question="boom?",
        model="gpt-4o-mini",
        error=RuntimeError("answer path blew up"),
    )

    assert record["outcome"] == "error"
    assert record["error_type"] == "RuntimeError"
    assert record["error_message"] == "answer path blew up"
    assert record["response_text"] == interaction_record.RUNTIME_FALLBACK_MESSAGE
    assert record["flags"] == []


def test_qa_review_context_is_applied_to_record() -> None:
    run = _data_assistant_run()
    context = interaction_record.QAReviewContext(
        battery_path="batteries/retail.yaml",
        qa_case_id="case-7",
        known_issues=(
            known_qa_issues.KnownQAIssue(
                issue_number=42,
                flag_category="correctness",
            ),
        ),
    )

    record = interaction_record.build_interaction_record(
        interaction_id="abc123",
        timestamp="2026-01-01T00:00:00+00:00",
        latency_ms=1,
        user="U123",
        question="q",
        qa_case_id=None,
        qa_review_context=context,
        model="m",
        result=run,
    )

    assert record["source"] == "qa_review"
    assert record["battery_path"] == "batteries/retail.yaml"
    assert record["qa_case_id"] == "case-7"
    assert record["known_issues"] == [
        {"issue_number": 42, "flag_category": "correctness"}
    ]


def test_qa_review_context_without_case_id_omits_known_issues() -> None:
    run = _data_assistant_run()
    context = interaction_record.QAReviewContext(
        battery_path="batteries/retail.yaml",
        qa_case_id=None,
    )

    record = interaction_record.build_interaction_record(
        interaction_id="abc123",
        timestamp="2026-01-01T00:00:00+00:00",
        latency_ms=1,
        user="U123",
        question="q",
        qa_case_id=None,
        qa_review_context=context,
        model="m",
        result=run,
    )

    assert record["source"] == "qa_review"
    assert record["battery_path"] == "batteries/retail.yaml"
    assert "qa_case_id" not in record
    assert "known_issues" not in record

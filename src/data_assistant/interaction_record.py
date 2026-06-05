"""Interaction Log record serialization for the Data Assistant.

This flat module owns the workflow-trace -> sanitized-record mapping for the
Interaction Log (the Decision Trail consumer, ADR-0016). It is a sibling of
``interaction_log.py``: that module owns ALL file I/O and the stdlib-only
serialize-whatever-dict store; THIS module owns the contract-aware step that
turns a workflow result (or a crash) into the flat, JSON-safe dict the store
appends.

The split keeps the dependency one-directional ``edge -> record``: the Slack
edge (the ``slack/`` package) imports ``build_interaction_record`` /
``build_error_record`` / ``QAReviewContext`` FROM here, so this module must NOT
import ``slack`` (that would be an import cycle). It owns the
canonical :data:`RUNTIME_FALLBACK_MESSAGE` text and
:func:`final_response_from_workflow_result` (both read/written here when building
records); the edge re-imports those for its block-rendering sites.

Sanitization (ADR-0016, CONTEXT.md): records carry the Question Frame, the routed
Data Request, the prepared-data SHAPE (rows x columns) + quality notes, and the
tiny ``key_data`` headline numbers -- but NEVER the bulk Prepared Data cell
values and never secrets.
"""

from __future__ import annotations

import dataclasses
import typing

import pandas as pd

import data_assistant.known_qa_issues as known_qa_issues
import data_assistant.workflow.contracts as contracts

RUNTIME_FALLBACK_MESSAGE = (
    "Something went wrong while answering your question. Please try again in a bit."
)
"""Adapter-level last-resort reply posted when an unexpected exception crashes
the answer path. This is a Runtime Fallback Message, NOT a Non-Answer Response:
it never routes through the Non-Answer Catalog and carries no reason or next
step. It is the canonical ``response_text`` recorded on an error line, and the
Slack edge also renders it as the fallback reply body. The Assistant transient
status auto-clears when this reply is sent, so no manual status clear is
needed."""


@dataclasses.dataclass(frozen=True)
class QAReviewContext:
    battery_path: str
    qa_case_id: str | None
    known_issues: tuple[known_qa_issues.KnownQAIssue, ...] = ()
    position: int | None = None
    total: int | None = None
    note_saved: bool = False


def final_response_from_workflow_result(
    result: contracts.WorkflowResult,
) -> contracts.FinalResponse:
    """Return the core workflow result's user-facing Final Response.

    Renders both real answers and Non-Answers to a ``FinalResponse`` (text +
    Trust-Summary blocks); the adapter just ``say``s whatever this returns.
    """
    if isinstance(result, contracts.FinalResponse):
        return result
    return result.final_response


def build_interaction_record(
    *,
    interaction_id: str,
    timestamp: str,
    latency_ms: int,
    user: str,
    question: str,
    qa_case_id: str | None,
    qa_review_context: QAReviewContext | None,
    model: str,
    result: contracts.WorkflowResult,
) -> dict[str, object]:
    """Build the sanitized Interaction Log record for a successful run.

    SUCCESS branches on the result type (ADR-0016): a ``DataAssistantRun`` is an
    answer; a bare ``FinalResponse`` is a Non-Answer. Either way the record
    carries the always-fields plus outcome-specific detail. It NEVER carries raw
    Prepared Data cell values (see ``_answer_fields``).
    """
    final_response = final_response_from_workflow_result(result)
    record: dict[str, object] = {
        "id": interaction_id,
        "timestamp": timestamp,
        "user": user,
        "question": question,
        "latency_ms": latency_ms,
        "response_text": final_response.text,
        "model": model,
        "flags": [],
    }
    if qa_case_id is not None:
        record["qa_case_id"] = qa_case_id
    _apply_qa_review_context(record, qa_review_context=qa_review_context)
    if isinstance(result, contracts.DataAssistantRun):
        record["outcome"] = "answer"
        record.update(_answer_fields(result))
    elif final_response.response_kind == contracts.ResponseKind.ANSWER:
        record["outcome"] = "answer"
    else:
        record["outcome"] = "non_answer"
        record.update(_non_answer_fields(final_response.non_answer))
    return record


def build_error_record(
    *,
    interaction_id: str,
    timestamp: str,
    latency_ms: int,
    user: str,
    question: str,
    model: str,
    error: BaseException,
    qa_review_context: QAReviewContext | None = None,
) -> dict[str, object]:
    """Build the Interaction Log record for a crashed answer path."""
    record: dict[str, object] = {
        "id": interaction_id,
        "timestamp": timestamp,
        "user": user,
        "question": question,
        "latency_ms": latency_ms,
        "response_text": RUNTIME_FALLBACK_MESSAGE,
        "model": model,
        "flags": [],
        "outcome": "error",
        "error_type": type(error).__name__,
        "error_message": str(error),
    }
    _apply_qa_review_context(record, qa_review_context=qa_review_context)
    return record


def _apply_qa_review_context(
    record: dict[str, object],
    *,
    qa_review_context: QAReviewContext | None,
) -> None:
    if qa_review_context is None:
        return
    record["source"] = "qa_review"
    record["battery_path"] = qa_review_context.battery_path
    if qa_review_context.qa_case_id is None:
        return
    record["qa_case_id"] = qa_review_context.qa_case_id
    record["known_issues"] = [
        {
            "issue_number": issue.issue_number,
            "flag_category": issue.flag_category,
        }
        for issue in qa_review_context.known_issues
    ]


def _answer_fields(run: contracts.DataAssistantRun) -> dict[str, object]:
    """Sanitized answer-specific fields from a successful run trace.

    Includes the Question Frame summary, the routed Data Request, the
    prepared-data SHAPE (rows x columns) + quality notes, and the tiny
    ``key_data`` headline numbers -- the ONE deliberate inclusion of cell values
    (ADR-0016). Bulk Prepared Data cell values are excluded by design.
    """
    data_request = run.data_request
    prepared = run.prepared_data
    rows, columns = prepared.data.shape
    return {
        "intent": run.question_frame.intent,
        "question_frame": _question_frame_summary(run.question_frame),
        "dataset": data_request.dataset.name,
        "metric": data_request.metric.label,
        "metric_expression": data_request.metric.expression,
        "group_by": (
            []
            if data_request.group_by_field is None
            else [data_request.group_by_field.label]
        ),
        "filters": list(data_request.filter_labels),
        "result_limit": data_request.result_limit,
        "prepared_data_shape": {"rows": int(rows), "columns": int(columns)},
        "quality_notes": list(prepared.quality_notes),
        "key_data": _key_data_records(run.answer_draft.key_data),
    }


def _non_answer_fields(non_answer: contracts.NonAnswer | None) -> dict[str, object]:
    """Non-Answer-specific fields read from FinalResponse.non_answer."""
    if non_answer is None:
        return {}
    return {
        "stage": str(non_answer.stage),
        "reason_code": str(non_answer.reason_code),
        "context": list(non_answer.context),
    }


def _question_frame_summary(
    question_frame: contracts.QuestionFrame,
) -> dict[str, object]:
    return {
        "intent": question_frame.intent,
        "metric": question_frame.metric,
        "time_scope": (
            None
            if question_frame.time_scope is None
            else str(question_frame.time_scope)
        ),
        "group_by": []
        if question_frame.group_by_field is None
        else [question_frame.group_by_field],
        "filters": list(question_frame.filter_labels),
        "unresolved_ambiguities": list(question_frame.unresolved_ambiguities),
    }


def _key_data_records(key_data: pd.DataFrame) -> list[dict[str, object]]:
    """Serialize the small ``key_data`` headline frame to JSON-safe records.

    ``key_data`` is a tiny ``pd.DataFrame`` (the headline rows). We turn it into
    a list of ``{column: value}`` dicts, coercing each value to a JSON-safe
    scalar so the line is greppable and never carries pandas/NumPy types. This
    is the deliberate, documented inclusion of cell values (ADR-0016); the bulk
    Prepared Data frame is never serialized.
    """
    records: list[dict[typing.Hashable, object]] = key_data.to_dict(orient="records")
    return [
        {str(column): _json_safe(value) for column, value in record.items()}
        for record in records
    ]


def _json_safe(value: object) -> object:
    if isinstance(value, bool | int | float | str) or value is None:
        return value
    return str(value)

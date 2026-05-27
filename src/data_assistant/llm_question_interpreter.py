"""Provider-backed Question Interpreter contract for Question Frame proposals."""

from __future__ import annotations

import collections.abc
import dataclasses
import datetime
import re
import typing

import data_assistant.semantic_layer.loader as semantic_layer_loader
import data_assistant.semantic_layer.schema as schema
import data_assistant.workflow.contracts as contracts

_UNSUPPORTED_DATA_PATTERNS = (
    re.compile(r"\bcsv\b"),
    re.compile(r"\bupload\b"),
    re.compile(r"\bspreadsheet\b"),
    re.compile(r"\bsql\b"),
    re.compile(r"\btable\b"),
    re.compile(r"\bdatabase\b"),
)
_UNSUPPORTED_DATA_REASON = "User-provided CSV files are not supported data sources."
_UNSUPPORTED_DATA_NEXT_STEP = (
    "Ask about an approved Curated Dataset in the Semantic Layer instead."
)
_REQUIRED_PROPOSAL_KEYS = frozenset(
    {"intent", "metric", "dimension", "time_range", "filters"}
)
_UNSAFE_AUTHORITY_KEYS = frozenset(
    {
        "dataset_id",
        "dataset_ids",
        "dataset_table",
        "dataset_tables",
        "table_id",
        "table_ids",
        "table_name",
        "table_names",
        "column",
        "columns",
        "column_id",
        "column_ids",
        "sql",
        "query",
        "metric_id",
        "metric_ids",
        "dimension_id",
        "dimension_ids",
    }
)
_SUPPORTED_PROVIDER_INTENTS = frozenset({"summarize"})


@dataclasses.dataclass(frozen=True)
class PromptContextDataset:
    """Business-facing Curated Dataset context for provider prompts."""

    dataset_id: str
    name: str
    information_types: tuple[str, ...]
    example_questions: tuple[str, ...]
    metric_labels: tuple[str, ...]
    dimension_labels: tuple[str, ...]


@dataclasses.dataclass(frozen=True)
class PromptContext:
    """Business-facing context passed to a Question Interpreter provider."""

    datasets: tuple[PromptContextDataset, ...]
    metric_labels: tuple[str, ...]
    dimension_labels: tuple[str, ...]
    supported_intents: tuple[str, ...]


@dataclasses.dataclass(frozen=True)
class QuestionFrameProposal:
    """Untrusted provider proposal shaped like a Question Frame."""

    intent: str
    metric: str
    dimension: str
    time_range: contracts.TimeRange | None
    filters: tuple[str, ...]


@dataclasses.dataclass(frozen=True)
class ProviderFailure:
    """Provider failed to produce a proposal."""

    reason: str


class QuestionInterpreterProvider(typing.Protocol):
    """Provider boundary for Question Frame proposals."""

    def propose_question_frame(
        self,
        *,
        question: str,
        prompt_context: PromptContext,
    ) -> object:
        """Return an untrusted Question Frame proposal or failure."""


ProposalMapping: typing.TypeAlias = dict[str, object]
TimeRangeMapping: typing.TypeAlias = dict[str, object]


def interpret_question(
    *,
    question: str,
    semantic_layer: schema.SemanticLayer,
    provider: QuestionInterpreterProvider,
) -> contracts.StageResult[contracts.QuestionFrame]:
    """Promote validated provider proposal into a trusted Question Frame."""
    normalized_question = _normalize(question)
    if _mentions_unsupported_data(normalized_question):
        return _non_answer(
            reason_code=contracts.NonAnswerReasonCode.UNSUPPORTED_DATA,
            reason=_UNSUPPORTED_DATA_REASON,
            unresolved_ambiguities=("unsupported data",),
            next_step=_UNSUPPORTED_DATA_NEXT_STEP,
        )

    prompt_context = build_prompt_context(semantic_layer)
    try:
        raw_provider_result = provider.propose_question_frame(
            question=question,
            prompt_context=prompt_context,
        )
    except Exception:
        return _provider_failure_non_answer()

    proposal_result = _normalize_provider_result(raw_provider_result)
    if isinstance(proposal_result, contracts.NonAnswer):
        return proposal_result
    proposal = proposal_result

    return _validate_proposal(proposal, prompt_context)


def build_prompt_context(semantic_layer: schema.SemanticLayer) -> PromptContext:
    """Collect business-facing prompt context from the Semantic Layer only."""
    datasets = tuple(
        PromptContextDataset(
            dataset_id=dataset.dataset_id,
            name=dataset.name,
            information_types=dataset.information_types,
            example_questions=dataset.example_questions,
            metric_labels=tuple(
                metric.label
                for table in semantic_layer_loader.tables_for_dataset(
                    dataset,
                    semantic_layer,
                )
                for metric in table.metrics
            ),
            dimension_labels=tuple(
                dimension.label
                for table in semantic_layer_loader.tables_for_dataset(
                    dataset,
                    semantic_layer,
                )
                for dimension in table.dimensions
            ),
        )
        for dataset in semantic_layer.datasets
    )
    metric_labels = tuple(
        metric.label
        for table in semantic_layer.tables
        for metric in table.metrics
    )
    dimension_labels = tuple(
        dimension.label
        for table in semantic_layer.tables
        for dimension in table.dimensions
    )
    return PromptContext(
        datasets=datasets,
        metric_labels=metric_labels,
        dimension_labels=dimension_labels,
        supported_intents=tuple(sorted(_SUPPORTED_PROVIDER_INTENTS)),
    )


def _normalize_provider_result(
    raw_provider_result: object,
) -> contracts.NonAnswer | QuestionFrameProposal:
    if isinstance(raw_provider_result, ProviderFailure):
        return _provider_failure_non_answer()
    if isinstance(raw_provider_result, QuestionFrameProposal):
        return raw_provider_result
    if not isinstance(raw_provider_result, dict):
        return _invalid_provider_output_non_answer()
    proposal_mapping = typing.cast(ProposalMapping, raw_provider_result)

    raw_keys = {str(key) for key in proposal_mapping}
    if raw_keys & _UNSAFE_AUTHORITY_KEYS:
        return _non_answer(
            reason_code=contracts.NonAnswerReasonCode.UNSAFE_AUTHORITY_DRIFT,
            reason=(
                "The Question Interpreter provider proposed retrieval authority "
                "it does not own."
            ),
            unresolved_ambiguities=("authority drift",),
            next_step=(
                "Remove dataset, table, SQL, and raw schema authority from the "
                "provider output."
            ),
        )
    if raw_keys != set(_REQUIRED_PROPOSAL_KEYS):
        return _invalid_provider_output_non_answer()

    intent = proposal_mapping.get("intent")
    metric = proposal_mapping.get("metric")
    dimension = proposal_mapping.get("dimension")
    time_range = proposal_mapping.get("time_range")
    filters = proposal_mapping.get("filters")
    if not all(isinstance(value, str) for value in (intent, metric, dimension)):
        return _invalid_provider_output_non_answer()
    if not isinstance(filters, (tuple, list)):
        return _invalid_provider_output_non_answer()
    filters_sequence = typing.cast(tuple[object, ...] | list[object], filters)
    if not all(isinstance(value, str) for value in filters_sequence):
        return _invalid_provider_output_non_answer()
    time_range_result = _normalize_time_range(time_range)
    if isinstance(time_range_result, contracts.NonAnswer):
        return time_range_result

    return QuestionFrameProposal(
        intent=typing.cast(str, intent),
        metric=typing.cast(str, metric),
        dimension=typing.cast(str, dimension),
        time_range=time_range_result,
        filters=tuple(typing.cast(collections.abc.Iterable[str], filters_sequence)),
    )


def _validate_proposal(
    proposal: QuestionFrameProposal,
    prompt_context: PromptContext,
) -> contracts.StageResult[contracts.QuestionFrame]:
    if proposal.intent not in _SUPPORTED_PROVIDER_INTENTS:
        return _non_answer(
            reason_code=contracts.NonAnswerReasonCode.UNSUPPORTED_INTENT,
            reason=(
                "The Data Assistant does not support that Data Question "
                "intent yet."
            ),
            unresolved_ambiguities=("supported intent",),
            next_step="Ask: What was total revenue by region in January 2026?",
        )
    if not proposal.metric:
        return _missing_required_field_non_answer("metric")
    if not proposal.dimension:
        return _missing_required_field_non_answer("dimension")

    if proposal.time_range is None:
        return _missing_required_field_non_answer("time range")
    time_range_result = _validate_time_range(proposal.time_range)
    if isinstance(time_range_result, contracts.NonAnswer):
        return time_range_result
    time_range = time_range_result
    if proposal.filters:
        return _non_answer(
            reason_code=contracts.NonAnswerReasonCode.UNSUPPORTED_FILTER,
            reason=(
                "The Data Assistant does not support provider-proposed "
                "filters yet."
            ),
            unresolved_ambiguities=("filters",),
            next_step="Ask the Data Question without filters for now.",
        )
    if proposal.metric not in prompt_context.metric_labels:
        return _unknown_semantic_label_non_answer("metric")
    if proposal.dimension not in prompt_context.dimension_labels:
        return _unknown_semantic_label_non_answer("dimension")

    return contracts.Success(
        contracts.QuestionFrame(
            intent=proposal.intent,
            metric=proposal.metric,
            dimension=proposal.dimension,
            time_range=time_range,
            filters=proposal.filters,
            unresolved_ambiguities=(),
        )
    )


def _missing_required_field_non_answer(field_name: str) -> contracts.NonAnswer:
    return _non_answer(
        reason_code=contracts.NonAnswerReasonCode.MISSING_REQUIRED_FIELD,
        reason="The Data Question is missing required interpretation details.",
        unresolved_ambiguities=(field_name,),
        next_step="Ask a clarification question before selecting data.",
    )


def _unknown_semantic_label_non_answer(field_name: str) -> contracts.NonAnswer:
    return _non_answer(
        reason_code=contracts.NonAnswerReasonCode.UNKNOWN_SEMANTIC_LABEL,
        reason=(
            "The Data Assistant could not match the requested Semantic Layer "
            "labels."
        ),
        unresolved_ambiguities=(field_name,),
        next_step="Use exact Semantic Layer metric and dimension labels.",
    )


def _provider_failure_non_answer() -> contracts.NonAnswer:
    return _non_answer(
        reason_code=contracts.NonAnswerReasonCode.PROVIDER_FAILURE,
        reason="The Question Interpreter provider could not produce a proposal.",
        unresolved_ambiguities=("provider failure",),
        next_step="Retry after the provider is available again.",
    )


def _invalid_provider_output_non_answer() -> contracts.NonAnswer:
    return _non_answer(
        reason_code=contracts.NonAnswerReasonCode.INVALID_PROVIDER_OUTPUT,
        reason="The Question Interpreter provider returned invalid output.",
        unresolved_ambiguities=("provider output",),
        next_step="Fix the provider contract before retrying.",
    )


def _non_answer(
    *,
    reason_code: contracts.NonAnswerReasonCode,
    reason: str,
    unresolved_ambiguities: tuple[str, ...],
    next_step: str,
) -> contracts.NonAnswer:
    return contracts.NonAnswer(
        stage="question_interpreter",
        reason_code=reason_code,
        reason=reason,
        unresolved_ambiguities=unresolved_ambiguities,
        next_step=next_step,
    )


def _normalize_time_range(
    raw_time_range: object,
) -> contracts.NonAnswer | contracts.TimeRange | None:
    if raw_time_range is None:
        return None
    if isinstance(raw_time_range, contracts.TimeRange):
        return _validate_time_range(raw_time_range)
    if not isinstance(raw_time_range, dict):
        return _invalid_time_range_non_answer()
    time_range_mapping = typing.cast(TimeRangeMapping, raw_time_range)
    if set(time_range_mapping) != {"label", "start_date", "end_date"}:
        return _invalid_time_range_non_answer()

    label = time_range_mapping.get("label")
    start_date = _normalize_date(time_range_mapping.get("start_date"))
    end_date = _normalize_date(time_range_mapping.get("end_date"))
    if not isinstance(label, str) or start_date is None or end_date is None:
        return _invalid_time_range_non_answer()

    time_range = contracts.TimeRange(
        label=label,
        start_date=start_date,
        end_date=end_date,
    )
    return _validate_time_range(time_range)


def _validate_time_range(
    time_range: contracts.TimeRange,
) -> contracts.NonAnswer | contracts.TimeRange:
    if time_range.start_date > time_range.end_date:
        return _invalid_time_range_non_answer()
    return time_range


def _normalize_date(raw_value: object) -> datetime.date | None:
    if isinstance(raw_value, datetime.date):
        return raw_value
    if not isinstance(raw_value, str):
        return None
    try:
        return datetime.date.fromisoformat(raw_value)
    except ValueError:
        return None


def _invalid_time_range_non_answer() -> contracts.NonAnswer:
    return _non_answer(
        reason_code=contracts.NonAnswerReasonCode.INVALID_PROVIDER_OUTPUT,
        reason="The Question Interpreter provider returned invalid output.",
        unresolved_ambiguities=("time range",),
        next_step="Fix the provider contract before retrying.",
    )


def _normalize(question: str) -> str:
    return " ".join(question.casefold().strip().split())


def _mentions_unsupported_data(normalized_question: str) -> bool:
    return any(
        pattern.search(normalized_question)
        for pattern in _UNSUPPORTED_DATA_PATTERNS
    )

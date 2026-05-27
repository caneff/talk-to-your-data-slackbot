"""Provider-backed Question Interpreter contract for Question Frame proposals."""

from __future__ import annotations

import collections.abc
import dataclasses
import datetime
import json
import typing

import pydantic

import data_assistant.question_interpreter_guards as interpreter_guards
import data_assistant.semantic_layer.loader as semantic_layer_loader
import data_assistant.semantic_layer.schema as schema
import data_assistant.workflow.contracts as contracts

_REQUIRED_PROPOSAL_KEYS = frozenset({
    "intent",
    "metric",
    "dimension",
    "time_range",
    "filters",
})
_UNSAFE_AUTHORITY_KEYS = frozenset({
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
})
_SUPPORTED_PROVIDER_INTENTS = frozenset({"summarize"})
_DEFAULT_OPENAI_MODEL = "gpt-5.5"


@dataclasses.dataclass(frozen=True)
class OpenAIQuestionInterpreterConfig:
    """Environment-backed config for the OpenAI Question Interpreter provider."""

    api_key: str
    model: str


class OpenAIQuestionInterpreterConfigError(ValueError):
    """Raised when required OpenAI provider config is missing."""


class OpenAITimeRangeProposal(pydantic.BaseModel):
    """Structured time range payload expected from OpenAI."""

    label: str
    start_date: datetime.date
    end_date: datetime.date


class OpenAIQuestionFrameProposal(pydantic.BaseModel):
    """Structured Question Frame proposal expected from OpenAI."""

    intent: str
    metric: str
    dimension: str
    time_range: OpenAITimeRangeProposal | None
    filters: tuple[str, ...]


@dataclasses.dataclass(frozen=True)
class ProviderFailure:
    """Provider failed to produce a proposal."""

    reason: str


def load_openai_question_interpreter_config(
    environ: collections.abc.Mapping[str, str],
) -> OpenAIQuestionInterpreterConfig:
    """Load required OpenAI provider config from environment variables."""
    if not environ.get("OPENAI_API_KEY"):
        raise OpenAIQuestionInterpreterConfigError(
            "Missing required OpenAI environment variables: OPENAI_API_KEY"
        )
    return OpenAIQuestionInterpreterConfig(
        api_key=environ["OPENAI_API_KEY"],
        model=environ.get("OPENAI_MODEL", _DEFAULT_OPENAI_MODEL),
    )


class _OpenAIResponsesClient(typing.Protocol):
    def parse(self, **kwargs: object) -> object:
        """Return one structured Responses API result."""


class _OpenAIClient(typing.Protocol):
    responses: _OpenAIResponsesClient


OpenAIClientFactory: typing.TypeAlias = collections.abc.Callable[..., _OpenAIClient]


class OpenAIQuestionInterpreterProvider:
    """OpenAI-backed Question Interpreter provider."""

    def __init__(
        self,
        *,
        config: OpenAIQuestionInterpreterConfig,
        client: _OpenAIClient,
    ) -> None:
        self._config = config
        self._client = client

    def propose_question_frame(
        self,
        *,
        question: str,
        prompt_context: dict[str, object],
    ) -> object:
        try:
            response = self._client.responses.parse(
                model=self._config.model,
                input=_build_openai_input(
                    question=question,
                    prompt_context=prompt_context,
                ),
                text_format=OpenAIQuestionFrameProposal,
            )
        except Exception as error:
            return ProviderFailure(reason=str(error) or "OpenAI provider failed")

        refusal = getattr(response, "refusal", None)
        if isinstance(refusal, str) and refusal:
            return ProviderFailure(reason=refusal)

        parsed_output = getattr(response, "output_parsed", None)
        if not isinstance(parsed_output, OpenAIQuestionFrameProposal):
            return {}
        proposal_dump = parsed_output.model_dump(mode="json")
        raw_filters = proposal_dump.get("filters")
        if isinstance(raw_filters, list):
            proposal_dump["filters"] = tuple(typing.cast(list[str], raw_filters))
        return typing.cast(dict[str, object], proposal_dump)


def _build_openai_input(
    *,
    question: str,
    prompt_context: dict[str, object],
) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "Interpret the Data Question into only the allowed structured "
                "Question Frame proposal fields. Use only business-facing "
                "Semantic Layer labels from the supplied context."
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {
                    "question": question,
                    "prompt_context": prompt_context,
                },
                sort_keys=True,
            ),
        },
    ]


def build_openai_question_interpreter_provider(
    environ: collections.abc.Mapping[str, str],
    *,
    client_factory: OpenAIClientFactory | None = None,
) -> OpenAIQuestionInterpreterProvider:
    """Build the OpenAI provider with env-backed config and a lazy SDK client."""
    config = load_openai_question_interpreter_config(environ)
    active_client_factory = client_factory
    if active_client_factory is None:
        active_client_factory = _default_openai_client_factory
    client = active_client_factory(api_key=config.api_key)
    return OpenAIQuestionInterpreterProvider(config=config, client=client)


def _default_openai_client_factory(*, api_key: str) -> _OpenAIClient:
    from openai import OpenAI

    return typing.cast(_OpenAIClient, OpenAI(api_key=api_key))


class QuestionInterpreterProvider(typing.Protocol):
    """Provider boundary for Question Frame proposals."""

    def propose_question_frame(
        self,
        *,
        question: str,
        prompt_context: dict[str, object],
    ) -> object:
        """Return an untrusted Question Frame proposal or failure."""


def interpret_question(
    *,
    question: str,
    semantic_layer: schema.SemanticLayer,
    provider: QuestionInterpreterProvider,
) -> contracts.StageResult[contracts.QuestionFrame]:
    """Promote validated provider proposal into a trusted Question Frame."""
    normalized_question = interpreter_guards.normalize_question(question)
    # Some requests are policy-level rejects; do not spend provider work on them.
    if interpreter_guards.mentions_unsupported_data(normalized_question):
        return interpreter_guards.unsupported_data_non_answer()

    # Prompt context is intentionally business-facing: labels and examples, not
    # table names, SQL, column names, or access internals.
    prompt_context = build_prompt_context(semantic_layer)
    try:
        raw_provider_result = provider.propose_question_frame(
            question=question,
            prompt_context=prompt_context,
        )
    except Exception:
        return _provider_failure_non_answer()

    # Provider output is only a proposal until schema and authority checks
    # promote it into the trusted Question Frame contract.
    return _promote_provider_result(raw_provider_result, semantic_layer)


def build_prompt_context(semantic_layer: schema.SemanticLayer) -> dict[str, object]:
    """Collect business-facing prompt context from the Semantic Layer only.

    Build up a dict of just what the Question Interpreter prompt should need (no IDs or
    table names for instance).
    """
    datasets: list[dict[str, object]] = []
    for dataset in semantic_layer.datasets:
        dataset_tables = semantic_layer_loader.tables_for_dataset(
            dataset,
            semantic_layer,
        )
        datasets.append({
            "name": dataset.name,
            "information_types": list(dataset.information_types),
            "example_questions": list(dataset.example_questions),
            "metric_labels": [
                metric.label for table in dataset_tables for metric in table.metrics
            ],
            "dimension_labels": [
                dimension.label
                for table in dataset_tables
                for dimension in table.dimensions
            ],
        })

    return {
        "datasets": datasets,
        "metric_labels": list(_metric_labels(semantic_layer)),
        "dimension_labels": list(_dimension_labels(semantic_layer)),
        "supported_intents": sorted(_SUPPORTED_PROVIDER_INTENTS),
    }


def _metric_labels(semantic_layer: schema.SemanticLayer) -> tuple[str, ...]:
    return tuple(
        metric.label for table in semantic_layer.tables for metric in table.metrics
    )


def _dimension_labels(semantic_layer: schema.SemanticLayer) -> tuple[str, ...]:
    return tuple(
        dimension.label
        for table in semantic_layer.tables
        for dimension in table.dimensions
    )


def _promote_provider_result(
    raw_provider_result: object,
    semantic_layer: schema.SemanticLayer,
) -> contracts.StageResult[contracts.QuestionFrame]:
    # First prove the provider returned a mapping we can inspect safely.
    if isinstance(raw_provider_result, ProviderFailure):
        return _provider_failure_non_answer()
    if not isinstance(raw_provider_result, dict):
        return _invalid_provider_output_non_answer()
    raw_mapping = typing.cast(dict[object, object], raw_provider_result)
    if not all(isinstance(key, str) for key in raw_mapping):
        return _invalid_provider_output_non_answer()
    proposal_mapping = typing.cast(dict[str, object], raw_mapping)

    # Then enforce the provider's boundary: Question Frame fields only, never
    # retrieval authority like datasets, tables, SQL, or schema identifiers.
    raw_keys = set(proposal_mapping)
    if raw_keys & _UNSAFE_AUTHORITY_KEYS:
        return contracts.NonAnswer(
            stage=contracts.NonAnswerStage.QUESTION_INTERPRETER,
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

    # Normalize provider values into concrete Python types before applying
    # workflow rules.
    intent_value = proposal_mapping["intent"]
    metric_value = proposal_mapping["metric"]
    dimension_value = proposal_mapping["dimension"]
    if (
        not isinstance(intent_value, str)
        or not isinstance(metric_value, str)
        or not isinstance(dimension_value, str)
    ):
        return _invalid_provider_output_non_answer()

    filters_value = _normalize_filters(proposal_mapping["filters"])
    if filters_value is None:
        return _invalid_provider_output_non_answer()

    time_range_result = _normalize_time_range(proposal_mapping["time_range"])
    if isinstance(time_range_result, contracts.NonAnswer):
        return time_range_result

    # Apply current workflow limits before promoting to trusted contract.
    if intent_value not in _SUPPORTED_PROVIDER_INTENTS:
        return contracts.NonAnswer(
            stage=contracts.NonAnswerStage.QUESTION_INTERPRETER,
            reason_code=contracts.NonAnswerReasonCode.UNSUPPORTED_INTENT,
            reason=(
                "The Data Assistant does not support that Data Question intent yet."
            ),
            unresolved_ambiguities=("supported intent",),
            next_step="Ask: What was total revenue by region in January 2026?",
        )
    if not metric_value:
        return _missing_required_field_non_answer("metric")
    if not dimension_value:
        return _missing_required_field_non_answer("dimension")

    if time_range_result is None:
        return _missing_required_field_non_answer("time range")
    time_range_value = time_range_result
    if filters_value:
        return contracts.NonAnswer(
            stage=contracts.NonAnswerStage.QUESTION_INTERPRETER,
            reason_code=contracts.NonAnswerReasonCode.UNSUPPORTED_FILTER,
            reason=(
                "The Data Assistant does not support provider-proposed filters yet."
            ),
            unresolved_ambiguities=("filters",),
            next_step="Ask the Data Question without filters for now.",
        )

    # Finally, prove provider labels are real Semantic Layer labels.
    if metric_value not in _metric_labels(semantic_layer):
        return _unknown_semantic_label_non_answer("metric")
    if dimension_value not in _dimension_labels(semantic_layer):
        return _unknown_semantic_label_non_answer("dimension")

    return contracts.Success(
        contracts.QuestionFrame(
            intent=intent_value,
            metric=metric_value,
            dimension=dimension_value,
            time_range=time_range_value,
            filters=filters_value,
            unresolved_ambiguities=(),
        )
    )


def _missing_required_field_non_answer(field_name: str) -> contracts.NonAnswer:
    return contracts.NonAnswer(
        stage=contracts.NonAnswerStage.QUESTION_INTERPRETER,
        reason_code=contracts.NonAnswerReasonCode.MISSING_REQUIRED_FIELD,
        reason="The Data Question is missing required interpretation details.",
        unresolved_ambiguities=(field_name,),
        next_step="Ask a clarification question before selecting data.",
    )


def _unknown_semantic_label_non_answer(field_name: str) -> contracts.NonAnswer:
    return contracts.NonAnswer(
        stage=contracts.NonAnswerStage.QUESTION_INTERPRETER,
        reason_code=contracts.NonAnswerReasonCode.UNKNOWN_SEMANTIC_LABEL,
        reason=(
            "The Data Assistant could not match the requested Semantic Layer labels."
        ),
        unresolved_ambiguities=(field_name,),
        next_step="Use exact Semantic Layer metric and dimension labels.",
    )


def _provider_failure_non_answer() -> contracts.NonAnswer:
    return contracts.NonAnswer(
        stage=contracts.NonAnswerStage.QUESTION_INTERPRETER,
        reason_code=contracts.NonAnswerReasonCode.PROVIDER_FAILURE,
        reason="The Question Interpreter provider could not produce a proposal.",
        unresolved_ambiguities=("provider failure",),
        next_step="Retry after the provider is available again.",
    )


def _invalid_provider_output_non_answer() -> contracts.NonAnswer:
    return contracts.NonAnswer(
        stage=contracts.NonAnswerStage.QUESTION_INTERPRETER,
        reason_code=contracts.NonAnswerReasonCode.INVALID_PROVIDER_OUTPUT,
        reason="The Question Interpreter provider returned invalid output.",
        unresolved_ambiguities=("provider output",),
        next_step="Fix the provider contract before retrying.",
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
    time_range_mapping = typing.cast(dict[str, object], raw_time_range)
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


def _normalize_filters(raw_filters: object) -> tuple[str, ...] | None:
    if not isinstance(raw_filters, (tuple, list)):
        return None

    raw_filter_values = typing.cast(tuple[object, ...] | list[object], raw_filters)
    filter_values: list[str] = []
    for value in raw_filter_values:
        if not isinstance(value, str):
            return None
        filter_values.append(value)
    return tuple(filter_values)


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
    return contracts.NonAnswer(
        stage=contracts.NonAnswerStage.QUESTION_INTERPRETER,
        reason_code=contracts.NonAnswerReasonCode.INVALID_PROVIDER_OUTPUT,
        reason="The Question Interpreter provider returned invalid output.",
        unresolved_ambiguities=("time range",),
        next_step="Fix the provider contract before retrying.",
    )

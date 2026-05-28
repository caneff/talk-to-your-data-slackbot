"""Provider-backed Question Interpreter contract for Question Frame proposals."""

from __future__ import annotations

import collections.abc
import dataclasses
import datetime
import functools
import importlib.resources
import json
import typing

import pydantic

import data_assistant.prompts as prompts
import data_assistant.question_interpreter_guards as interpreter_guards
import data_assistant.semantic_layer.loader as semantic_layer_loader
import data_assistant.semantic_layer.schema as schema
import data_assistant.workflow.contracts as contracts

_SUPPORTED_PROVIDER_INTENTS = frozenset({"summarize"})
_DEFAULT_OPENAI_MODEL = "gpt-5.5"
OpenAIInputMessage: typing.TypeAlias = dict[str, str]
_QUESTION_INTERPRETER_DEVELOPER_PROMPT = "question_interpreter_developer.md"


@dataclasses.dataclass(frozen=True)
class OpenAIQuestionInterpreterConfig:
    """Environment-backed config for the OpenAI Question Interpreter provider."""

    api_key: str
    model: str


class OpenAIQuestionInterpreterConfigError(ValueError):
    """Raised when required OpenAI provider config is missing."""


class TimeRangeProposal(pydantic.BaseModel):
    """Untrusted provider proposal for a Question Frame time range."""

    model_config = pydantic.ConfigDict(extra="forbid")

    label: str
    start_date: datetime.date
    end_date: datetime.date


class QuestionFrameProposal(pydantic.BaseModel):
    """Untrusted provider proposal shape for a Question Frame."""

    model_config = pydantic.ConfigDict(extra="forbid")

    intent: str | None
    metric: str | None
    dimension: str | None
    time_range: TimeRangeProposal | None
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
        semantic_layer_context: dict[str, object],
    ) -> QuestionFrameProposal | ProviderFailure:
        try:
            response = self._client.responses.parse(
                model=self._config.model,
                input=_build_openai_input(
                    question=question,
                    semantic_layer_context=semantic_layer_context,
                ),
                text_format=QuestionFrameProposal,
            )
        except Exception as error:
            return ProviderFailure(reason=str(error) or "OpenAI provider failed")

        refusal = getattr(response, "refusal", None)
        if isinstance(refusal, str) and refusal:
            return ProviderFailure(reason=refusal)

        parsed_output = getattr(response, "output_parsed", None)
        if not isinstance(parsed_output, QuestionFrameProposal):
            return ProviderFailure(reason="OpenAI provider returned no parsed output")
        return parsed_output


def _build_openai_input(
    *,
    question: str,
    semantic_layer_context: dict[str, object],
) -> list[OpenAIInputMessage]:
    return [
        _developer_message(),
        _user_message(
            question=question,
            semantic_layer_context=semantic_layer_context,
        ),
    ]


def _developer_message() -> OpenAIInputMessage:
    return {
        "role": "developer",
        "content": _developer_instructions(),
    }


@functools.cache
def _developer_instructions() -> str:
    return (
        importlib.resources
        .files(prompts)
        .joinpath(_QUESTION_INTERPRETER_DEVELOPER_PROMPT)
        .read_text(encoding="utf-8")
        .strip()
    )


def _user_message(
    *,
    question: str,
    semantic_layer_context: dict[str, object],
) -> OpenAIInputMessage:
    return {
        "role": "user",
        "content": json.dumps(
            {
                "question": question,
                "semantic_layer_context": semantic_layer_context,
            },
            sort_keys=True,
        ),
    }


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
        semantic_layer_context: dict[str, object],
    ) -> QuestionFrameProposal | ProviderFailure:
        """Return an untrusted Question Frame proposal or failure."""
        ...


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

    # Semantic Layer context is intentionally business-facing: labels and
    # examples, not table names, SQL, column names, or access internals.
    semantic_layer_context = build_semantic_layer_context(semantic_layer)
    try:
        raw_provider_result = provider.propose_question_frame(
            question=question,
            semantic_layer_context=semantic_layer_context,
        )
    except Exception:
        return _provider_failure_non_answer()

    # Provider output is only a proposal until workflow validation promotes it
    # into the trusted Question Frame contract.
    return _promote_provider_result(raw_provider_result, semantic_layer)


def build_semantic_layer_context(
    semantic_layer: schema.SemanticLayer,
) -> dict[str, object]:
    """Collect business-facing context from the Semantic Layer only.

    Build just what the Question Interpreter should need: labels, examples, and
    supported intents, without IDs, table names, SQL, columns, or access internals.
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
            "available_metric_labels": sorted({
                metric.label for table in dataset_tables for metric in table.metrics
            }),
            "available_dimension_labels": sorted({
                dimension.label
                for table in dataset_tables
                for dimension in table.dimensions
            }),
        })

    return {
        "datasets": datasets,
        "all_metric_labels": sorted(set(_metric_labels(semantic_layer))),
        "all_dimension_labels": sorted(set(_dimension_labels(semantic_layer))),
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
    if isinstance(raw_provider_result, ProviderFailure):
        return _provider_failure_non_answer()
    if not isinstance(raw_provider_result, QuestionFrameProposal):
        return _invalid_provider_output_non_answer()

    proposal = raw_provider_result
    intent_value = proposal.intent
    metric_value = proposal.metric
    dimension_value = proposal.dimension

    time_range_result = _normalize_time_range(proposal.time_range)
    if isinstance(time_range_result, contracts.NonAnswer):
        return time_range_result

    # Apply current workflow limits before promoting to trusted contract.
    if not intent_value:
        return _missing_required_field_non_answer("intent")
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
    if proposal.filters:
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
            filters=proposal.filters,
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
    if not isinstance(raw_time_range, TimeRangeProposal):
        return _invalid_time_range_non_answer()

    time_range = contracts.TimeRange(
        label=raw_time_range.label,
        start_date=raw_time_range.start_date,
        end_date=raw_time_range.end_date,
    )
    return _validate_time_range(time_range)


def _validate_time_range(
    time_range: contracts.TimeRange,
) -> contracts.NonAnswer | contracts.TimeRange:
    if time_range.start_date > time_range.end_date:
        return _invalid_time_range_non_answer()
    return time_range


def _invalid_time_range_non_answer() -> contracts.NonAnswer:
    return contracts.NonAnswer(
        stage=contracts.NonAnswerStage.QUESTION_INTERPRETER,
        reason_code=contracts.NonAnswerReasonCode.INVALID_PROVIDER_OUTPUT,
        reason="The Question Interpreter provider returned invalid output.",
        unresolved_ambiguities=("time range",),
        next_step="Fix the provider contract before retrying.",
    )

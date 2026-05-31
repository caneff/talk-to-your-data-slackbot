"""Provider-backed Question Interpreter contract for Question Frame proposals."""

from __future__ import annotations

import collections.abc
import dataclasses
import datetime
import decimal
import functools
import importlib.resources
import json
import typing

import pydantic
from openai import OpenAI

import data_assistant.non_answer_catalog as non_answer_catalog
import data_assistant.prompts as prompts
import data_assistant.question_interpreter_guards as interpreter_guards
import data_assistant.semantic_layer.loader as semantic_layer_loader
import data_assistant.semantic_layer.schema as schema
import data_assistant.workflow.contracts as contracts

_SUPPORTED_PROVIDER_INTENTS = frozenset({"summarize"})
_DEFAULT_OPENAI_MODEL = "gpt-4o-mini"
OpenAIInputMessage: typing.TypeAlias = dict[str, str]
_QUESTION_INTERPRETER_DEVELOPER_PROMPT = "question_interpreter_developer.md"


@dataclasses.dataclass(frozen=True)
class OpenAIQuestionInterpreterConfig:
    """Environment-backed config for the OpenAI Question Interpreter provider."""

    api_key: str
    model: str


class OpenAIQuestionInterpreterConfigError(ValueError):
    """Raised when required OpenAI provider config is missing."""


class FieldOperationProposal(pydantic.BaseModel):
    """Untrusted provider proposal for one Semantic Field operation."""

    model_config = pydantic.ConfigDict(extra="forbid")

    operation: typing.Literal[
        "group_by",
        "range_filter",
        "include_filter",
        "exclude_filter",
    ] = pydantic.Field(
        description=(
            "Use group_by for requested grouping, range_filter for complete "
            "calendar months or date ranges, include_filter for exact dates or "
            "included values, and exclude_filter for excluded values."
        ),
    )
    field: str = pydantic.Field(
        description="Business-facing Semantic Field label from semantic_layer_context.",
    )
    lower: str | None = pydantic.Field(
        default=None,
        description=(
            "Lower range_filter value. Use ISO YYYY-MM-DD for date ranges. "
            "Null for group_by, include_filter, and exclude_filter."
        ),
    )
    upper: str | None = pydantic.Field(
        default=None,
        description=(
            "Upper range_filter value. Use ISO YYYY-MM-DD for date ranges. "
            "Null for group_by, include_filter, and exclude_filter."
        ),
    )
    values: tuple[str, ...] = pydantic.Field(
        default=(),
        description=(
            "Values for include_filter or exclude_filter. Empty for group_by "
            "and range_filter."
        ),
    )


GroupByOperationProposal = FieldOperationProposal
RangeFilterOperationProposal = FieldOperationProposal
IncludeFilterOperationProposal = FieldOperationProposal
ExcludeFilterOperationProposal = FieldOperationProposal


class QuestionFrameProposal(pydantic.BaseModel):
    """Untrusted provider proposal shape for a Question Frame."""

    model_config = pydantic.ConfigDict(extra="forbid")

    intent: str | None = pydantic.Field(
        description=(
            "Use summarize for supported Data Questions that ask for historical "
            "metric totals, summaries, or grouped results, including phrases "
            "like 'what was', 'show', and 'summarize'. Use null only when no "
            "supported intent applies."
        ),
    )
    metric: str | None = pydantic.Field(
        description=(
            "Business-facing Semantic Metric label from semantic_layer_context, "
            "or null when no matching metric is present."
        ),
    )
    field_operations: tuple[FieldOperationProposal, ...] = pydantic.Field(
        description=(
            "Every explicit grouping, date constraint, and filter from the "
            "Data Question, represented with Semantic Field labels."
        ),
    )


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

        refusal = _extract_response_refusal(response)
        if refusal:
            return ProviderFailure(reason=refusal)

        parsed_output = getattr(response, "output_parsed", None)
        if not isinstance(parsed_output, QuestionFrameProposal):
            return ProviderFailure(reason="OpenAI provider returned no parsed output")
        return parsed_output


def _extract_response_refusal(response: object) -> str | None:
    output_items = typing.cast(
        collections.abc.Iterable[object],
        getattr(response, "output", ()),
    )
    for output_item in output_items:
        if getattr(output_item, "type", None) != "message":
            continue
        content_items = typing.cast(
            collections.abc.Iterable[object],
            getattr(output_item, "content", ()),
        )
        for content_item in content_items:
            if getattr(content_item, "type", None) != "refusal":
                continue
            refusal = getattr(content_item, "refusal", None)
            if isinstance(refusal, str) and refusal:
                return refusal
    return None


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
    client: _OpenAIClient | None = None,
) -> OpenAIQuestionInterpreterProvider:
    """Build the OpenAI provider with env-backed config and SDK client."""
    config = load_openai_question_interpreter_config(environ)
    return OpenAIQuestionInterpreterProvider(
        config=config,
        client=client or _build_openai_client(config.api_key),
    )


def _build_openai_client(api_key: str) -> _OpenAIClient:
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
        return non_answer_catalog.non_answer(
            contracts.NonAnswerReasonCode.UNSUPPORTED_DATA,
            stage=contracts.NonAnswerStage.QUESTION_INTERPRETER,
        )

    # Semantic Layer context is intentionally business-facing: labels and
    # examples, not table names, SQL, column names, or access internals.
    semantic_layer_context = build_semantic_layer_context(semantic_layer)
    try:
        raw_provider_result = provider.propose_question_frame(
            question=question,
            semantic_layer_context=semantic_layer_context,
        )
    except Exception:
        return non_answer_catalog.non_answer(
            contracts.NonAnswerReasonCode.PROVIDER_FAILURE,
            stage=contracts.NonAnswerStage.QUESTION_INTERPRETER,
        )

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
            "available_fields": sorted(
                [
                    {
                        "label": field.label,
                        "data_type": field.data_type,
                        "operations": sorted(
                            operation.value for operation in field.operations
                        ),
                    }
                    for table in dataset_tables
                    for field in table.fields
                ],
                key=lambda field_context: typing.cast(str, field_context["label"]),
            ),
            "available_field_labels": sorted({
                field.label
                for table in dataset_tables
                for field in table.fields
            }),
        })

    return {
        "datasets": datasets,
        "all_metric_labels": sorted(set(_metric_labels(semantic_layer))),
        "all_field_labels": sorted(set(_field_labels(semantic_layer))),
        "supported_intents": sorted(_SUPPORTED_PROVIDER_INTENTS),
    }


def _metric_labels(semantic_layer: schema.SemanticLayer) -> tuple[str, ...]:
    return tuple(
        metric.label for table in semantic_layer.tables for metric in table.metrics
    )


def _field_labels(semantic_layer: schema.SemanticLayer) -> tuple[str, ...]:
    return tuple(
        field.label
        for table in semantic_layer.tables
        for field in table.fields
    )


def _promote_provider_result(
    raw_provider_result: object,
    semantic_layer: schema.SemanticLayer,
) -> contracts.StageResult[contracts.QuestionFrame]:
    if isinstance(raw_provider_result, ProviderFailure):
        return non_answer_catalog.non_answer(
            contracts.NonAnswerReasonCode.PROVIDER_FAILURE,
            stage=contracts.NonAnswerStage.QUESTION_INTERPRETER,
        )
    if not isinstance(raw_provider_result, QuestionFrameProposal):
        return non_answer_catalog.non_answer(
            contracts.NonAnswerReasonCode.INVALID_PROVIDER_OUTPUT,
            stage=contracts.NonAnswerStage.QUESTION_INTERPRETER,
        )

    proposal = raw_provider_result
    intent_value = proposal.intent
    metric_value = proposal.metric

    # Apply current workflow limits before promoting to trusted contract.
    if not intent_value:
        return non_answer_catalog.missing_required_field_non_answer(
            "intent",
            stage=contracts.NonAnswerStage.QUESTION_INTERPRETER,
        )
    if intent_value not in _SUPPORTED_PROVIDER_INTENTS:
        return non_answer_catalog.non_answer(
            contracts.NonAnswerReasonCode.UNSUPPORTED_INTENT,
            stage=contracts.NonAnswerStage.QUESTION_INTERPRETER,
        )
    if not metric_value:
        return non_answer_catalog.missing_required_field_non_answer(
            "metric",
            stage=contracts.NonAnswerStage.QUESTION_INTERPRETER,
        )

    # Finally, prove provider labels are real Semantic Layer labels.
    if metric_value not in _metric_labels(semantic_layer):
        return non_answer_catalog.unknown_semantic_label_non_answer(
            "metric",
            stage=contracts.NonAnswerStage.QUESTION_INTERPRETER,
        )
    field_operations_result = _promote_field_operations(
        proposal.field_operations,
        semantic_layer,
    )
    if isinstance(field_operations_result, contracts.NonAnswer):
        return field_operations_result

    return contracts.Success(
        contracts.QuestionFrame(
            intent=intent_value,
            metric=metric_value,
            field_operations=field_operations_result,
            unresolved_ambiguities=(),
        )
    )


def _promote_field_operations(
    operation_proposals: tuple[FieldOperationProposal, ...],
    semantic_layer: schema.SemanticLayer,
) -> contracts.NonAnswer | tuple[contracts.SemanticFieldOperation, ...]:
    fields_by_label = {
        field.label: field for table in semantic_layer.tables for field in table.fields
    }
    promoted_operations: list[contracts.SemanticFieldOperation] = []
    group_by_count = 0
    for operation_proposal in operation_proposals:
        field = fields_by_label.get(operation_proposal.field)
        if field is None:
            return non_answer_catalog.unknown_semantic_label_non_answer(
                "field",
                stage=contracts.NonAnswerStage.QUESTION_INTERPRETER,
            )
        operation = schema.FieldOperation(operation_proposal.operation)
        if operation not in field.operations:
            return non_answer_catalog.non_answer(
                contracts.NonAnswerReasonCode.UNSUPPORTED_FIELD_OPERATION,
                stage=contracts.NonAnswerStage.QUESTION_INTERPRETER,
            )
        if operation == schema.FieldOperation.GROUP_BY:
            group_by_count += 1
            if group_by_count > 1:
                return non_answer_catalog.non_answer(
                    contracts.NonAnswerReasonCode.UNSUPPORTED_SHAPE,
                    stage=contracts.NonAnswerStage.QUESTION_INTERPRETER,
                )
            promoted_operations.append(
                contracts.SemanticFieldOperation(
                    operation=operation,
                    field=field.label,
                )
            )
            continue
        if operation == schema.FieldOperation.RANGE_FILTER:
            result = _promote_range_filter(operation_proposal, field, operation)
        elif operation in {
            schema.FieldOperation.INCLUDE_FILTER,
            schema.FieldOperation.EXCLUDE_FILTER,
        }:
            result = _promote_values_filter(operation_proposal, field, operation)
        else:
            return non_answer_catalog.non_answer(
                contracts.NonAnswerReasonCode.INVALID_PROVIDER_OUTPUT,
                stage=contracts.NonAnswerStage.QUESTION_INTERPRETER,
            )
        if isinstance(result, contracts.NonAnswer):
            return result
        promoted_operations.append(result)

    return tuple(promoted_operations)


def _promote_range_filter(
    operation_proposal: FieldOperationProposal,
    field: schema.SemanticField,
    operation: schema.FieldOperation,
) -> contracts.NonAnswer | contracts.SemanticFieldOperation:
    if operation_proposal.lower is None and operation_proposal.upper is None:
        return non_answer_catalog.non_answer(
            contracts.NonAnswerReasonCode.INVALID_PROVIDER_OUTPUT,
            stage=contracts.NonAnswerStage.QUESTION_INTERPRETER,
        )
    lower = (
        None
        if operation_proposal.lower is None
        else _coerce_field_value(operation_proposal.lower, field)
    )
    if isinstance(lower, contracts.NonAnswer):
        return lower
    upper = (
        None
        if operation_proposal.upper is None
        else _coerce_field_value(operation_proposal.upper, field)
    )
    if isinstance(upper, contracts.NonAnswer):
        return upper
    if _range_bounds_are_reversed(lower, upper):
        return non_answer_catalog.non_answer(
            contracts.NonAnswerReasonCode.INVALID_PROVIDER_OUTPUT,
            stage=contracts.NonAnswerStage.QUESTION_INTERPRETER,
        )
    return contracts.SemanticFieldOperation(
        operation=operation,
        field=field.label,
        lower=lower,
        upper=upper,
    )


def _range_bounds_are_reversed(
    lower: contracts.FieldValue | None,
    upper: contracts.FieldValue | None,
) -> bool:
    if lower is None or upper is None:
        return False
    if isinstance(lower, datetime.date) and isinstance(upper, datetime.date):
        return lower > upper
    if isinstance(lower, decimal.Decimal) and isinstance(upper, decimal.Decimal):
        return lower > upper
    if isinstance(lower, str) and isinstance(upper, str):
        return lower > upper
    return False


def _promote_values_filter(
    operation_proposal: FieldOperationProposal,
    field: schema.SemanticField,
    operation: schema.FieldOperation,
) -> contracts.NonAnswer | contracts.SemanticFieldOperation:
    if not operation_proposal.values:
        return non_answer_catalog.non_answer(
            contracts.NonAnswerReasonCode.INVALID_PROVIDER_OUTPUT,
            stage=contracts.NonAnswerStage.QUESTION_INTERPRETER,
        )
    coerced_values: list[contracts.FieldValue] = []
    for value in operation_proposal.values:
        coerced_value = _coerce_field_value(value, field)
        if isinstance(coerced_value, contracts.NonAnswer):
            return coerced_value
        coerced_values.append(coerced_value)
    return contracts.SemanticFieldOperation(
        operation=operation,
        field=field.label,
        values=tuple(coerced_values),
    )


def _coerce_field_value(
    value: str,
    field: schema.SemanticField,
) -> contracts.FieldValue | contracts.NonAnswer:
    if field.data_type == schema.DataType.DATE:
        try:
            return datetime.date.fromisoformat(value)
        except ValueError:
            return non_answer_catalog.non_answer(
                contracts.NonAnswerReasonCode.INVALID_PROVIDER_OUTPUT,
                stage=contracts.NonAnswerStage.QUESTION_INTERPRETER,
            )
    if field.data_type == schema.DataType.DECIMAL:
        try:
            coerced_value = decimal.Decimal(value)
        except decimal.InvalidOperation:
            return non_answer_catalog.non_answer(
                contracts.NonAnswerReasonCode.INVALID_PROVIDER_OUTPUT,
                stage=contracts.NonAnswerStage.QUESTION_INTERPRETER,
            )
        if not coerced_value.is_finite():
            return non_answer_catalog.non_answer(
                contracts.NonAnswerReasonCode.INVALID_PROVIDER_OUTPUT,
                stage=contracts.NonAnswerStage.QUESTION_INTERPRETER,
            )
        return coerced_value
    if field.data_type == schema.DataType.STRING:
        return value
    return non_answer_catalog.non_answer(
        contracts.NonAnswerReasonCode.INVALID_PROVIDER_OUTPUT,
        stage=contracts.NonAnswerStage.QUESTION_INTERPRETER,
    )

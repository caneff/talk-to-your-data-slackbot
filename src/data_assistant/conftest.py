"""Shared pytest fixtures for Data Assistant workflow tests."""

import typing

import pytest

import data_assistant.access_controller as access_controller
import data_assistant.data_requester as data_requester
import data_assistant.local_duckdb_fixture as local_duckdb_fixture
import data_assistant.question_interpreter as question_interpreter
import data_assistant.semantic_layer.catalog as semantic_layer_catalog
import data_assistant.semantic_layer.schema as schema
import data_assistant.semantic_matcher as semantic_matcher
import data_assistant.semantic_router as semantic_router
import data_assistant.workflow.contracts as contracts

CANONICAL_DATA_QUESTION = "What was total revenue by region in January 2026?"
T = typing.TypeVar("T")


def unwrap_stage_result(result: contracts.StageResult[T]) -> T:
    """Return a successful stage value or fail the test with the NonAnswer."""
    if isinstance(result, contracts.NonAnswer):
        raise AssertionError(result)
    return result.value


class StaticQuestionInterpreterProvider:
    """Deterministic test double for the LLM question interpreter provider."""

    def __init__(
        self,
        proposal: question_interpreter.QuestionFrameProposal,
    ) -> None:
        self._proposal = proposal

    def propose_question_frame(
        self,
        *,
        question: str,
        semantic_layer_context: dict[str, object],
    ) -> question_interpreter.QuestionFrameProposal:
        """Return the configured proposal without calling an LLM."""
        del question, semantic_layer_context
        return self._proposal


def canonical_question_proposal() -> question_interpreter.QuestionFrameProposal:
    """Return provider proposal for the canonical revenue-by-region question."""
    return question_interpreter.QuestionFrameProposal(
        intent="summarize",
        metric="total revenue",
        field_operations=(
            question_interpreter.GroupByOperationProposal(
                operation="group_by",
                field="region",
            ),
            question_interpreter.RangeFilterOperationProposal(
                operation="range_filter",
                field="order date",
                lower="2026-01-01",
                upper="2026-01-31",
            ),
        ),
    )


def missing_time_scope_proposal() -> question_interpreter.QuestionFrameProposal:
    """Return provider proposal that omits required time scope."""
    return question_interpreter.QuestionFrameProposal(
        intent="summarize",
        metric="total revenue",
        field_operations=(
            question_interpreter.GroupByOperationProposal(
                operation="group_by",
                field="region",
            ),
        ),
    )


def canonical_test_semantic_layer() -> semantic_layer_catalog.SemanticLayerCatalog:
    """Build the small orders+customers layer shared by workflow tests.

    Workflow integration tests pair this layer with the in-memory ``orders``
    DuckDB fixture (order_date / region / revenue). It is intentionally
    self-contained and not parsed from the on-disk retail layer, so the canonical
    end-to-end fixtures stay decoupled from the shipped dataset's exact shape.
    """
    return semantic_layer_catalog.SemanticLayerCatalog(
        datasets=(
            schema.CuratedDataset(
                dataset_id="retail_ops",
                name="Retail Operations",
                tables=("orders", "customers"),
                information_types=(
                    "revenue",
                    "regional performance",
                    "order activity",
                    "customer metadata",
                ),
                example_questions=(
                    "What was total revenue by region in January 2026?",
                    "What was customer count by customer region in January 2026?",
                ),
                dataset_access=schema.DatasetAccess(
                    allowed_identity_ids=(
                        "employee_123",
                        "local_development_user",
                    ),
                ),
            ),
        ),
        tables=(
            schema.DatasetTable(
                table_id="orders",
                dataset_id="retail_ops",
                description="Clean retail order facts.",
                columns=(
                    schema.TableColumn(column_id="order_date", data_type="date"),
                    schema.TableColumn(column_id="region", data_type="string"),
                    schema.TableColumn(column_id="revenue", data_type="decimal"),
                ),
                metrics=(
                    schema.Metric(
                        metric_id="total_revenue",
                        label="total revenue",
                        expression="sum(revenue)",
                        source_column="revenue",
                        kind=schema.MetricKind.MONEY,
                    ),
                ),
                fields=(
                    schema.SemanticField(
                        field_id="order_date",
                        label="order date",
                        source_column="order_date",
                        data_type=schema.DataType.DATE,
                        operations=(
                            schema.FieldOperation.GROUP_BY,
                            schema.FieldOperation.INCLUDE_FILTER,
                            schema.FieldOperation.EXCLUDE_FILTER,
                            schema.FieldOperation.RANGE_FILTER,
                        ),
                    ),
                    schema.SemanticField(
                        field_id="region",
                        label="region",
                        source_column="region",
                        data_type=schema.DataType.STRING,
                        operations=(
                            schema.FieldOperation.GROUP_BY,
                            schema.FieldOperation.INCLUDE_FILTER,
                            schema.FieldOperation.EXCLUDE_FILTER,
                        ),
                    ),
                ),
            ),
            schema.DatasetTable(
                table_id="customers",
                dataset_id="retail_ops",
                description="Clean retail customer metadata.",
                columns=(
                    schema.TableColumn(column_id="created_date", data_type="date"),
                    schema.TableColumn(column_id="customer_id", data_type="string"),
                    schema.TableColumn(column_id="customer_region", data_type="string"),
                ),
                metrics=(
                    schema.Metric(
                        metric_id="customer_count",
                        label="customer count",
                        expression="count(customer_id)",
                        source_column="customer_id",
                        kind=schema.MetricKind.COUNT,
                    ),
                ),
                fields=(
                    schema.SemanticField(
                        field_id="created_date",
                        label="created date",
                        source_column="created_date",
                        data_type=schema.DataType.DATE,
                        operations=(
                            schema.FieldOperation.INCLUDE_FILTER,
                            schema.FieldOperation.EXCLUDE_FILTER,
                            schema.FieldOperation.RANGE_FILTER,
                        ),
                    ),
                    schema.SemanticField(
                        field_id="customer_region",
                        label="customer region",
                        source_column="customer_region",
                        data_type=schema.DataType.STRING,
                        operations=(
                            schema.FieldOperation.GROUP_BY,
                            schema.FieldOperation.INCLUDE_FILTER,
                            schema.FieldOperation.EXCLUDE_FILTER,
                        ),
                    ),
                ),
            ),
        ),
    )


@pytest.fixture
def active_semantic_layer() -> semantic_layer_catalog.SemanticLayerCatalog:
    """Return the canonical orders+customers Semantic Layer for workflow tests."""
    return canonical_test_semantic_layer()


@pytest.fixture
def connect_orders() -> local_duckdb_fixture.OrdersConnector:
    """Expose the in-memory DuckDB orders connector as a fixture."""
    return local_duckdb_fixture.connect_orders


@pytest.fixture
def canonical_question() -> str:
    """Return the shared question covered by the demo dataset."""
    return CANONICAL_DATA_QUESTION


@pytest.fixture
def allowed_internal_identity() -> contracts.InternalIdentity:
    """Return an identity allowed to access the demo retail dataset."""
    return access_controller.DEFAULT_LOCAL_ALLOWED_IDENTITY


@pytest.fixture
def canonical_question_provider() -> question_interpreter.QuestionInterpreterProvider:
    """Return a fake provider that can answer the canonical question."""
    return StaticQuestionInterpreterProvider(canonical_question_proposal())


@pytest.fixture
def missing_time_scope_provider() -> question_interpreter.QuestionInterpreterProvider:
    """Return a fake provider that triggers missing-time-scope NonAnswer."""
    return StaticQuestionInterpreterProvider(missing_time_scope_proposal())


@pytest.fixture
def question_frame(
    canonical_question: str,
    active_semantic_layer: semantic_layer_catalog.SemanticLayerCatalog,
    canonical_question_provider: question_interpreter.QuestionInterpreterProvider,
) -> contracts.QuestionFrame:
    """Build a valid Question Frame through the interpreter boundary."""
    return unwrap_stage_result(
        question_interpreter.interpret_question(
            question=canonical_question,
            semantic_layer=active_semantic_layer,
            provider=canonical_question_provider,
        ),
    )


@pytest.fixture
def semantic_matches(
    question_frame: contracts.QuestionFrame,
    active_semantic_layer: semantic_layer_catalog.SemanticLayerCatalog,
) -> tuple[contracts.SemanticMatch, ...]:
    """Build canonical Semantic Layer matches through the matcher boundary."""
    return semantic_matcher.find_semantic_matches(
        question_frame,
        active_semantic_layer,
    )


@pytest.fixture
def dataset_selection(
    semantic_matches: tuple[contracts.SemanticMatch, ...],
) -> contracts.DatasetSelection:
    """Build the canonical Dataset Selection through the semantic router."""
    return unwrap_stage_result(semantic_router.select_dataset(semantic_matches))


@pytest.fixture
def available_data_resolution(
    question_frame: contracts.QuestionFrame,
    active_semantic_layer: semantic_layer_catalog.SemanticLayerCatalog,
) -> contracts.AvailableDataResolution:
    """Build canonical Available Data through the semantic router."""
    return unwrap_stage_result(
        semantic_router.resolve_available_data(
            question_frame,
            active_semantic_layer,
        )
    )


@pytest.fixture
def data_request(
    question_frame: contracts.QuestionFrame,
    available_data_resolution: contracts.AvailableDataResolution,
) -> contracts.DataRequest:
    """Build the canonical Data Request through the requester boundary."""
    return data_requester.create_data_request(
        question_frame,
        available_data_resolution,
    )

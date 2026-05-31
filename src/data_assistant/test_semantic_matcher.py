import datetime

import data_assistant.semantic_layer.schema as schema
import data_assistant.semantic_matcher as semantic_matcher
import data_assistant.workflow.contracts as contracts


def test_semantic_matcher_resolves_canonical_table_level_match(
    active_semantic_layer: schema.SemanticLayer,
) -> None:
    matches = semantic_matcher.find_semantic_matches(
        _question_frame(metric="total revenue", field="region"),
        active_semantic_layer,
    )

    assert len(matches) == 1
    match = matches[0]
    assert match.dataset.dataset_id == "commerce"
    assert match.table.table_id == "orders"
    assert match.metric.metric_id == "total_revenue"
    assert match.group_by_fields[0].field_id == "region"


def test_semantic_matcher_requires_metric_and_dimension_on_same_table(
    active_semantic_layer: schema.SemanticLayer,
) -> None:
    matches = semantic_matcher.find_semantic_matches(
        _question_frame(metric="customer count", field="region"),
        active_semantic_layer,
    )

    assert matches == ()


def test_semantic_matcher_uses_exact_labels_not_semantic_ids(
    active_semantic_layer: schema.SemanticLayer,
) -> None:
    matches = semantic_matcher.find_semantic_matches(
        _question_frame(metric="total_revenue", field="region"),
        active_semantic_layer,
    )

    assert matches == ()


def _question_frame(
    *,
    metric: str,
    field: str,
) -> contracts.QuestionFrame:
    return contracts.QuestionFrame(
        intent="summarize",
        metric=metric,
        field_operations=(
            contracts.SemanticFieldOperation(
                operation=contracts.FieldOperationKind.GROUP_BY,
                field=field,
            ),
            contracts.SemanticFieldOperation(
                operation=contracts.FieldOperationKind.RANGE_FILTER,
                field="order date",
                lower=datetime.date(2026, 1, 1),
                upper=datetime.date(2026, 1, 31),
            ),
        ),
        unresolved_ambiguities=(),
    )

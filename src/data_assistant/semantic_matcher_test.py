import datetime

import data_assistant.semantic_layer.catalog as semantic_layer_catalog
import data_assistant.semantic_matcher as semantic_matcher
import data_assistant.workflow.contracts as contracts


def test_semantic_matcher_resolves_canonical_table_level_match(
    active_semantic_layer: semantic_layer_catalog.SemanticLayerCatalog,
) -> None:
    matches = semantic_matcher.find_semantic_matches(
        _question_frame(metric="total revenue", field="region"),
        active_semantic_layer,
    )

    assert len(matches) == 1
    match = matches[0]
    assert match.dataset.dataset_id == "retail_ops"
    assert match.table.table_id == "orders"
    assert match.metric.metric_id == "total_revenue"
    assert match.group_by_field is not None
    assert match.group_by_field.field_id == "region"


def test_semantic_matcher_requires_metric_and_dimension_on_same_table(
    active_semantic_layer: semantic_layer_catalog.SemanticLayerCatalog,
) -> None:
    matches = semantic_matcher.find_semantic_matches(
        _question_frame(metric="customer count", field="region"),
        active_semantic_layer,
    )

    assert matches == ()


def test_semantic_matcher_uses_exact_labels_not_semantic_ids(
    active_semantic_layer: semantic_layer_catalog.SemanticLayerCatalog,
) -> None:
    matches = semantic_matcher.find_semantic_matches(
        _question_frame(metric="total_revenue", field="region"),
        active_semantic_layer,
    )

    assert matches == ()


def test_semantic_matcher_resolves_month_calendar_grouping_on_date_field(
    active_semantic_layer: semantic_layer_catalog.SemanticLayerCatalog,
) -> None:
    question_frame = contracts.QuestionFrame(
        intent="summarize",
        metric="total revenue",
        time_scope=contracts.TimeScope.BOUNDED,
        group_by_field=None,
        field_filters=(
            contracts.RangeFilter(
                field="order date",
                lower=datetime.date(2026, 1, 1),
                upper=datetime.date(2026, 12, 31),
            ),
        ),
        unresolved_ambiguities=(),
        calendar_grouping=contracts.CalendarGrouping(
            field="order date",
            grain=contracts.CalendarGrain.MONTH,
        ),
    )

    matches = semantic_matcher.find_semantic_matches(
        question_frame,
        active_semantic_layer,
    )

    assert len(matches) == 1
    match = matches[0]
    assert match.group_by_field is None
    assert match.calendar_grouping is not None
    assert match.calendar_grouping.field.field_id == "order_date"
    assert match.calendar_grouping.grain == contracts.CalendarGrain.MONTH


def _question_frame(
    *,
    metric: str,
    field: str,
) -> contracts.QuestionFrame:
    return contracts.QuestionFrame(
        intent="summarize",
        metric=metric,
        time_scope=contracts.TimeScope.BOUNDED,
        group_by_field=field,
        field_filters=(
            contracts.RangeFilter(
                field="order date",
                lower=datetime.date(2026, 1, 1),
                upper=datetime.date(2026, 1, 31),
            ),
        ),
        unresolved_ambiguities=(),
    )

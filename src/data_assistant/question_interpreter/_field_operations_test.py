from __future__ import annotations

import decimal

import data_assistant.question_interpreter as question_interpreter
import data_assistant.question_interpreter._field_operations as field_operations
import data_assistant.semantic_layer.schema as schema
import data_assistant.semantic_layer.testing_support as semantic_layer_testing
import data_assistant.workflow.contracts as contracts


def test_validate_field_filters_rejects_duplicate_semantic_field_labels() -> None:
    semantic_layer = semantic_layer_testing.semantic_layer_with_table(
        columns={
            "order_date": "date",
            "region_dimension": "varchar",
            "region_grouping": "varchar",
            "revenue": "decimal",
        },
        fields=(
            schema.SemanticField(
                field_id="region_dimension",
                label="region",
                source_column="region_dimension",
                data_type=schema.DataType.STRING,
                operations=(schema.FieldOperation.INCLUDE_FILTER,),
            ),
            schema.SemanticField(
                field_id="region_grouping",
                label="region",
                source_column="region_grouping",
                data_type=schema.DataType.STRING,
                operations=(schema.FieldOperation.GROUP_BY,),
            ),
        ),
    )

    result = field_operations.validate_field_filters(
        (
            question_interpreter.ProviderFieldOperation(
                operation="include_filter",
                field="region",
                values=("east",),
            ),
        ),
        semantic_layer,
        None,
    )

    assert isinstance(result, contracts.NonAnswer)
    assert result.reason_code == contracts.NonAnswerReasonCode.INVALID_PROVIDER_OUTPUT


def test_duplicate_field_labels_are_rejected_even_when_contracts_match() -> None:
    semantic_layer = semantic_layer_testing.semantic_layer_with_table(
        columns={
            "order_date": "date",
            "region_east": "varchar",
            "region_west": "varchar",
            "revenue": "decimal",
        },
        fields=(
            schema.SemanticField(
                field_id="region_east",
                label="region",
                source_column="region_east",
                data_type=schema.DataType.STRING,
                operations=(schema.FieldOperation.INCLUDE_FILTER,),
            ),
            schema.SemanticField(
                field_id="region_west",
                label="region",
                source_column="region_west",
                data_type=schema.DataType.STRING,
                operations=(schema.FieldOperation.INCLUDE_FILTER,),
            ),
        ),
    )

    result = field_operations.validate_field_filters(
        (
            question_interpreter.ProviderFieldOperation(
                operation="include_filter",
                field="region",
                values=("east",),
            ),
        ),
        semantic_layer,
        None,
    )

    assert isinstance(result, contracts.NonAnswer)
    assert result.reason_code == contracts.NonAnswerReasonCode.INVALID_PROVIDER_OUTPUT


def test_unrelated_duplicate_field_labels_do_not_block_unique_field_validation() -> (
    None
):
    semantic_layer = semantic_layer_testing.semantic_layer_with_table(
        columns={
            "order_date": "date",
            "region_east": "varchar",
            "region_west": "varchar",
            "revenue": "decimal",
        },
        fields=(
            schema.SemanticField(
                field_id="region_east",
                label="region",
                source_column="region_east",
                data_type=schema.DataType.STRING,
                operations=(schema.FieldOperation.INCLUDE_FILTER,),
            ),
            schema.SemanticField(
                field_id="region_west",
                label="region",
                source_column="region_west",
                data_type=schema.DataType.STRING,
                operations=(schema.FieldOperation.INCLUDE_FILTER,),
            ),
            schema.SemanticField(
                field_id="revenue",
                label="revenue",
                source_column="revenue",
                data_type=schema.DataType.DECIMAL,
                operations=(schema.FieldOperation.INCLUDE_FILTER,),
            ),
        ),
    )

    result = field_operations.validate_field_filters(
        (
            question_interpreter.ProviderFieldOperation(
                operation="include_filter",
                field="revenue",
                values=("10.50",),
            ),
        ),
        semantic_layer,
        None,
    )

    assert result == (
        None,
        (
            contracts.ValuesFilter(
                field="revenue",
                mode=contracts.FilterMode.INCLUDE,
                values=(decimal.Decimal("10.50"),),
            ),
        ),
    )


def test_validate_field_filters_coerces_decimal_values_filters() -> None:
    semantic_layer = semantic_layer_testing.semantic_layer_with_table(
        fields=(
            schema.SemanticField(
                field_id="revenue",
                label="revenue",
                source_column="revenue",
                data_type=schema.DataType.DECIMAL,
                operations=(schema.FieldOperation.INCLUDE_FILTER,),
            ),
        ),
    )

    result = field_operations.validate_field_filters(
        (
            question_interpreter.ProviderFieldOperation(
                operation="include_filter",
                field="revenue",
                values=("10.50", "20"),
            ),
        ),
        semantic_layer,
        None,
    )

    assert result == (
        None,
        (
            contracts.ValuesFilter(
                field="revenue",
                mode=contracts.FilterMode.INCLUDE,
                values=(decimal.Decimal("10.50"), decimal.Decimal("20")),
            ),
        ),
    )


def test_validate_field_filters_coerces_decimal_range_bounds() -> None:
    semantic_layer = semantic_layer_testing.semantic_layer_with_table(
        fields=(
            schema.SemanticField(
                field_id="revenue",
                label="revenue",
                source_column="revenue",
                data_type=schema.DataType.DECIMAL,
                operations=(schema.FieldOperation.RANGE_FILTER,),
            ),
        ),
    )

    result = field_operations.validate_field_filters(
        (
            question_interpreter.ProviderFieldOperation(
                operation="range_filter",
                field="revenue",
                lower="10.50",
                upper="20",
            ),
        ),
        semantic_layer,
        None,
    )

    assert result == (
        None,
        (
            contracts.RangeFilter(
                field="revenue",
                lower=decimal.Decimal("10.50"),
                upper=decimal.Decimal("20"),
            ),
        ),
    )

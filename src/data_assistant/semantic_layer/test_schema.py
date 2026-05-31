import data_assistant.semantic_layer.schema as schema


def test_data_type_has_exactly_one_member_per_logical_type() -> None:
    assert set(schema.DataType) == {
        schema.DataType.DATE,
        schema.DataType.DECIMAL,
        schema.DataType.STRING,
    }


def test_data_type_drops_collapsed_synonyms() -> None:
    member_names = {member.name for member in schema.DataType}
    assert "NUMBER" not in member_names
    assert "VARCHAR" not in member_names

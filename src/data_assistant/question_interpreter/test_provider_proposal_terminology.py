import data_assistant.question_interpreter as question_interpreter


def test_package_facade_exports_provider_proposal_terms_only() -> None:
    assert question_interpreter.ProviderProposal is not None
    assert question_interpreter.ProviderFieldOperation is not None
    assert "ProviderProposal" in question_interpreter.__all__
    assert "ProviderFieldOperation" in question_interpreter.__all__
    assert "QuestionFrameProposal" not in question_interpreter.__all__
    assert "FieldOperationProposal" not in question_interpreter.__all__

    for removed_name in (
        "QuestionFrameProposal",
        "FieldOperationProposal",
        "GroupByOperationProposal",
        "RangeFilterOperationProposal",
        "IncludeFilterOperationProposal",
        "ExcludeFilterOperationProposal",
    ):
        assert not hasattr(question_interpreter, removed_name)


def test_provider_proposal_schema_uses_new_model_names() -> None:
    response_schema = question_interpreter.ProviderProposal.model_json_schema()

    assert response_schema["title"] == "ProviderProposal"
    assert "ProviderFieldOperation" in response_schema["$defs"]
    assert "FieldOperationProposal" not in response_schema["$defs"]

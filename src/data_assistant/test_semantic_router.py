import datetime

import data_assistant.semantic_layer.schema as schema
import data_assistant.semantic_matcher as semantic_matcher
import data_assistant.semantic_router as semantic_router
import data_assistant.workflow.contracts as contracts


def test_dataset_selection_chooses_one_curated_dataset_with_rationale(
    dataset_selection: contracts.DatasetSelection,
) -> None:
    assert len(dataset_selection.selected_datasets) == 1
    assert dataset_selection.selected_datasets[0].dataset_id == "commerce"
    assert "total revenue metric and region dimension" in (
        dataset_selection.match_rationale
    )


def test_semantic_router_returns_non_answer_when_no_dataset_matches(
    active_semantic_layer: schema.SemanticLayer,
) -> None:
    question_frame = contracts.QuestionFrame(
        intent="summarize",
        metric="gross bookings",
        dimension="region",
        time_range=contracts.TimeRange(
            label="January 2026",
            start_date=datetime.date(2026, 1, 1),
            end_date=datetime.date(2026, 1, 31),
        ),
        filters=(),
        unresolved_ambiguities=(),
    )
    semantic_matches = semantic_matcher.find_semantic_matches(
        question_frame,
        active_semantic_layer,
    )

    result = semantic_router.select_dataset(semantic_matches)

    assert result == contracts.NonAnswer(
        stage=contracts.NonAnswerStage.SEMANTIC_ROUTER,
        reason_code=contracts.NonAnswerReasonCode.NO_MATCHING_DATASET,
        reason="No Curated Dataset safely matches the Question Frame.",
        unresolved_ambiguities=("curated dataset",),
        next_step="Ask which approved business data should be used.",
    )

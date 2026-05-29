import data_assistant.llm_question_interpreter as llm_question_interpreter
import data_assistant.semantic_layer.loader as semantic_layer_loader


def test_build_semantic_layer_context_uses_only_business_facing_fields() -> None:
    semantic_layer = semantic_layer_loader.load_semantic_layer()

    semantic_layer_context = llm_question_interpreter.build_semantic_layer_context(
        semantic_layer
    )

    assert semantic_layer_context == {
        "datasets": [
            {
                "name": "Commerce Revenue",
                "information_types": [
                    "revenue",
                    "regional performance",
                    "order activity",
                    "customer metadata",
                ],
                "example_questions": [
                    "What was total revenue by region in January 2026?",
                ],
                "available_metric_labels": ["customer count", "total revenue"],
                "available_dimension_labels": ["customer region", "region"],
            },
        ],
        "all_metric_labels": ["customer count", "total revenue"],
        "all_dimension_labels": ["customer region", "region"],
        "supported_intents": ["summarize"],
    }

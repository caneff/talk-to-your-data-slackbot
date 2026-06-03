import typing

import pandas as pd
import pytest

import data_assistant.non_answer_catalog as non_answer_catalog
import data_assistant.response_composer as response_composer
import data_assistant.semantic_layer.schema as schema
import data_assistant.workflow.contracts as contracts


def _non_answer(
    reason_code: contracts.NonAnswerReasonCode = (
        contracts.NonAnswerReasonCode.UNSUPPORTED_DATA
    ),
    *,
    stage: contracts.NonAnswerStage = contracts.NonAnswerStage.QUESTION_INTERPRETER,
    datasets: tuple[str, ...] = (),
) -> contracts.NonAnswer:
    return contracts.NonAnswer(
        stage=stage,
        reason_code=reason_code,
        datasets=datasets,
    )


def test_response_composer_returns_plain_text_with_trust_summary() -> None:
    response = response_composer.compose_final_response(
        contracts.AnswerDraft(
            summary=(
                "Total revenue in January 2026 was $2,050.00, grouped across 2 regions."
            ),
            key_data=pd.DataFrame(
                {
                    "dimension_value": ("North", "South"),
                    "metric_value": (1200.0, 850.0),
                }
            ),
            datasets_used=("Commerce",),
            dataset_tables_used=("orders",),
            metric_kind=schema.MetricKind.MONEY,
            metric_label="total revenue",
            time_range="January 2026",
            filters=(),
            caveats=("1 row excluded because revenue was missing.",),
            group_by_label="region",
        )
    )

    assert response.response_kind == contracts.ResponseKind.ANSWER
    assert (
        "Total revenue in January 2026 was $2,050.00, grouped across 2 regions."
        in response.text
    )
    assert "- North: $1,200.00" in response.text
    assert "- South: $850.00" in response.text
    assert "Trust Summary:" in response.text
    assert response.trust_summary == contracts.TrustSummary(
        datasets=("Commerce",),
        dataset_tables=("orders",),
        time_range="January 2026",
        filters=(),
        caveats=("1 row excluded because revenue was missing.",),
        limitations=(),
    )


def test_response_composer_returns_visible_slack_blocks_for_answer_package() -> None:
    response = response_composer.compose_final_response(
        contracts.AnswerDraft(
            summary=(
                "Total revenue in January 2026 was $2,050.00, grouped across 2 regions."
            ),
            key_data=pd.DataFrame(
                {
                    "dimension_value": ("North", "South"),
                    "metric_value": (1200.0, 850.0),
                }
            ),
            datasets_used=("Commerce",),
            dataset_tables_used=("orders",),
            metric_kind=schema.MetricKind.MONEY,
            metric_label="total revenue",
            time_range="January 2026",
            filters=(),
            caveats=("1 row excluded because revenue was missing.",),
            group_by_label="region",
        )
    )

    assert response.blocks == (
        {
            "type": "section",
            "text": {
                "type": "plain_text",
                "text": (
                    "Total revenue in January 2026 was $2,050.00, grouped across "
                    "2 regions."
                ),
            },
        },
        {
            "type": "context",
            "elements": [
                {
                    "type": "plain_text",
                    "text": (
                        "Trust Summary: Curated Dataset: Commerce. Dataset Table: "
                        "orders. Time range: January 2026. Caveats: 1 row "
                        "excluded because revenue was missing."
                    ),
                },
            ],
        },
        {
            "type": "table",
            "column_settings": [
                {"is_wrapped": True},
                {"align": "right"},
            ],
            "rows": [
                [
                    {"type": "raw_text", "text": "Region"},
                    {"type": "raw_text", "text": "Total Revenue"},
                ],
                [
                    {"type": "raw_text", "text": "North"},
                    {"type": "raw_text", "text": "$1,200.00"},
                ],
                [
                    {"type": "raw_text", "text": "South"},
                    {"type": "raw_text", "text": "$850.00"},
                ],
            ],
        },
    )


def test_response_composer_formats_count_rows_from_metric_kind() -> None:
    response = response_composer.compose_final_response(
        contracts.AnswerDraft(
            summary=(
                "Customer count in January 2026 was 2,050, grouped across 2 regions."
            ),
            key_data=pd.DataFrame(
                {
                    "dimension_value": ("North", "South"),
                    "metric_value": (1200, 850),
                }
            ),
            datasets_used=("Commerce Customers",),
            dataset_tables_used=("customers",),
            metric_kind=schema.MetricKind.COUNT,
            metric_label="customer count",
            time_range="January 2026",
            filters=(),
            caveats=(),
        )
    )

    assert "- North: 1,200" in response.text
    assert "- South: 850" in response.text
    assert "$1,200.00" not in response.text


def test_response_composer_title_cases_each_word_in_table_headers() -> None:
    response = response_composer.compose_final_response(
        contracts.AnswerDraft(
            summary="Customer count in all available data was 2,050.",
            key_data=pd.DataFrame(
                {
                    "dimension_value": ("All",),
                    "metric_value": (2050,),
                }
            ),
            datasets_used=("Commerce Customers",),
            dataset_tables_used=("customers",),
            metric_kind=schema.MetricKind.COUNT,
            metric_label="customer count",
            time_range="all available data",
            filters=(),
            caveats=(),
        )
    )

    table_block = response.blocks[2]
    assert table_block["type"] == "table"
    rows = typing.cast(list[list[dict[str, str]]], table_block["rows"])
    assert rows[0] == [
        {"type": "raw_text", "text": "Group"},
        {"type": "raw_text", "text": "Customer Count"},
    ]


def test_response_composer_renders_through_injected_wording_provider() -> None:
    """Composer renders Non-Answer copy through the injected provider.

    A fake provider returning sentinel wording proves the composer no longer
    hardcodes the catalog call but threads the injected provider's output.
    """

    class _SentinelWordingProvider:
        def render_wording(
            self,
            non_answer: contracts.NonAnswer,
        ) -> non_answer_catalog.NonAnswerWording:
            del non_answer
            return non_answer_catalog.NonAnswerWording(
                reason="Sentinel reason.",
                next_step="Sentinel step.",
            )

    response = response_composer.compose_non_answer_response(
        _non_answer(contracts.NonAnswerReasonCode.UNSUPPORTED_DATA),
        wording_provider=_SentinelWordingProvider(),
    )

    assert "I cannot answer safely because sentinel reason." in response.text
    assert "Next step: Sentinel step." in response.text
    assert response.trust_summary.limitations == ("Sentinel reason.",)


def test_response_composer_carries_non_answer_on_final_response() -> None:
    """The Non-Answer is carried on ``FinalResponse.non_answer`` for the log.

    The Interaction Log (ADR-0016) reads the FINE 15-way ``reason_code`` and
    ``stage`` off this field instead of the coarse 4-bucket ``ResponseKind``.
    """
    non_answer = _non_answer(
        contracts.NonAnswerReasonCode.MISSING_TIME_SCOPE,
        stage=contracts.NonAnswerStage.QUESTION_INTERPRETER,
    )

    response = response_composer.compose_non_answer_response(
        non_answer,
        wording_provider=non_answer_catalog.StaticCatalogWording(),
    )

    assert response.non_answer is non_answer


def test_response_composer_leaves_non_answer_none_on_answer() -> None:
    response = response_composer.compose_final_response(
        contracts.AnswerDraft(
            summary="Total revenue in January 2026 was $1,200.00.",
            key_data=pd.DataFrame(
                {
                    "dimension_value": ("North",),
                    "metric_value": (1200.0,),
                }
            ),
            datasets_used=("Commerce",),
            dataset_tables_used=("orders",),
            metric_kind=schema.MetricKind.MONEY,
            metric_label="total revenue",
            time_range="January 2026",
            filters=(),
            caveats=(),
            group_by_label="region",
        )
    )

    assert response.non_answer is None


def test_response_composer_renders_non_answer_copy_into_text() -> None:
    """Composer weaves the catalog-rendered reason and next step into the text.

    Exact wording is the catalog golden test's job; here we assert the composer
    threads whatever the catalog renders through its template and trust summary.
    """
    non_answer = _non_answer(contracts.NonAnswerReasonCode.UNSUPPORTED_DATA)
    wording = non_answer_catalog.render_wording(non_answer)
    lowercased_reason = wording.reason[0].lower() + wording.reason[1:]

    response = response_composer.compose_non_answer_response(
        non_answer,
        wording_provider=non_answer_catalog.StaticCatalogWording(),
    )

    assert response.response_kind == contracts.ResponseKind.UNSUPPORTED
    assert f"I cannot answer safely because {lowercased_reason}" in response.text
    assert f"Next step: {wording.next_step}" in response.text
    assert response.trust_summary == contracts.TrustSummary(
        limitations=(wording.reason,),
    )


def test_response_composer_marks_clarification_non_answers_with_yet_wording() -> None:
    non_answer = _non_answer(
        contracts.NonAnswerReasonCode.MISSING_REQUIRED_FIELD,
    )
    wording = non_answer_catalog.render_wording(non_answer)

    response = response_composer.compose_non_answer_response(
        non_answer,
        wording_provider=non_answer_catalog.StaticCatalogWording(),
    )

    assert response.response_kind == contracts.ResponseKind.CLARIFICATION_NEEDED
    assert response.text.startswith("I cannot answer safely yet because")
    assert wording.reason in response.trust_summary.limitations
    assert wording.next_step in response.text


@pytest.mark.parametrize(
    "reason_code",
    [
        contracts.NonAnswerReasonCode.AMBIGUOUS_DATASET,
        contracts.NonAnswerReasonCode.AMBIGUOUS_TABLE,
    ],
    ids=lambda code: code.name,
)
def test_response_composer_marks_ambiguity_as_clarification(
    reason_code: contracts.NonAnswerReasonCode,
) -> None:
    non_answer = _non_answer(reason_code)
    wording = non_answer_catalog.render_wording(non_answer)

    response = response_composer.compose_non_answer_response(
        non_answer,
        wording_provider=non_answer_catalog.StaticCatalogWording(),
    )

    assert response.response_kind == contracts.ResponseKind.CLARIFICATION_NEEDED
    assert response.text.startswith("I cannot answer safely yet because")
    assert wording.next_step in response.text


@pytest.mark.parametrize(
    "reason_code",
    [
        contracts.NonAnswerReasonCode.UNSUPPORTED_DATA,
        contracts.NonAnswerReasonCode.NO_MATCHING_DATASET,
        contracts.NonAnswerReasonCode.PROVIDER_FAILURE,
    ],
    ids=lambda code: code.name,
)
def test_response_composer_marks_unsupported_non_answers_without_yet_wording(
    reason_code: contracts.NonAnswerReasonCode,
) -> None:
    non_answer = _non_answer(reason_code)
    wording = non_answer_catalog.render_wording(non_answer)

    response = response_composer.compose_non_answer_response(
        non_answer,
        wording_provider=non_answer_catalog.StaticCatalogWording(),
    )

    assert response.response_kind == contracts.ResponseKind.UNSUPPORTED
    assert response.text.startswith("I cannot answer safely because")
    assert "safely yet" not in response.text
    assert wording.next_step in response.text


def test_response_composer_omits_sensitive_details_from_access_denial() -> None:
    response = response_composer.compose_non_answer_response(
        non_answer_catalog.access_denied_non_answer(
            "commerce",
            stage=contracts.NonAnswerStage.ACCESS_CONTROLLER,
        ),
        wording_provider=non_answer_catalog.StaticCatalogWording(),
    )

    assert "Curated Dataset: commerce." in response.text
    assert "Dataset Table:" not in response.text
    assert "Filters:" not in response.text

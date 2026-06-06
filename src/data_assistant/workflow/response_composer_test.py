import typing

import pandas as pd
import pytest

import data_assistant.non_answer_catalog as non_answer_catalog
import data_assistant.semantic_layer.schema as schema
import data_assistant.workflow.contracts as contracts
import data_assistant.workflow.response_composer as response_composer


def _non_answer(
    reason_code: contracts.NonAnswerReasonCode = (
        contracts.NonAnswerReasonCode.UNSUPPORTED_INTENT
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
            datasets_used=("Retail Operations",),
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
        datasets=("Retail Operations",),
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
            datasets_used=("Retail Operations",),
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
                        "Trust Summary: Curated Dataset: Retail Operations. "
                        "Dataset Table: orders. Time range: January 2026. "
                        "Caveats: 1 row excluded because revenue was missing."
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
            datasets_used=("Retail Customers",),
            dataset_tables_used=("customers",),
            metric_kind=schema.MetricKind.COUNT,
            metric_label="customer count",
            time_range="January 2026",
            filters=(),
            caveats=(),
            group_by_label="region",
        )
    )

    assert "- North: 1,200" in response.text
    assert "- South: 850" in response.text
    assert "$1,200.00" not in response.text


def test_response_composer_title_cases_each_word_in_table_headers() -> None:
    response = response_composer.compose_final_response(
        contracts.AnswerDraft(
            summary="Customer count in January 2026 was 2,050 across 2 regions.",
            key_data=pd.DataFrame(
                {
                    "dimension_value": ("North", "South"),
                    "metric_value": (1200, 850),
                }
            ),
            datasets_used=("Retail Customers",),
            dataset_tables_used=("customers",),
            metric_kind=schema.MetricKind.COUNT,
            metric_label="customer count",
            time_range="January 2026",
            filters=(),
            caveats=(),
            group_by_label="region",
        )
    )

    table_block = response.blocks[2]
    assert table_block["type"] == "table"
    rows = typing.cast(list[list[dict[str, str]]], table_block["rows"])
    assert rows[0] == [
        {"type": "raw_text", "text": "Region"},
        {"type": "raw_text", "text": "Customer Count"},
    ]


def test_response_composer_suppresses_redundant_all_bullet_and_table_when_ungrouped() -> (  # noqa: E501
    None
):
    """Ungrouped single-total answers omit the redundant ``- All:`` bullet+table.

    For an ungrouped answer (``group_by_label is None``) the single ``All`` row
    just repeats the headline number the summary already states, so the metric
    bullet and the one-row key-data table block are suppressed (issue #275). The
    secondary narrative bug is split out to #281 and not addressed here.
    """
    response = response_composer.compose_final_response(
        contracts.AnswerDraft(
            summary="In Q1 2026, Total net revenue totaled $122,441.75.",
            key_data=pd.DataFrame(
                {
                    "dimension_value": ("All",),
                    "metric_value": (122441.75,),
                }
            ),
            datasets_used=("Retail Operations",),
            dataset_tables_used=("orders",),
            metric_kind=schema.MetricKind.MONEY,
            metric_label="total net revenue",
            time_range="Q1 2026",
            filters=(),
            caveats=(),
        )
    )

    assert response.response_kind == contracts.ResponseKind.ANSWER
    assert "In Q1 2026, Total net revenue totaled $122,441.75." in response.text
    assert "- All:" not in response.text
    assert "$122,441.75" in response.text  # only in the summary headline
    assert response.text.count("$122,441.75") == 1
    assert "Trust Summary:" in response.text
    assert "table" not in {block["type"] for block in response.blocks}
    assert response.blocks == (
        {
            "type": "section",
            "text": {
                "type": "plain_text",
                "text": "In Q1 2026, Total net revenue totaled $122,441.75.",
            },
        },
        {
            "type": "context",
            "elements": [
                {
                    "type": "plain_text",
                    "text": (
                        "Trust Summary: Curated Dataset: Retail Operations. "
                        "Dataset Table: orders. Time range: Q1 2026."
                    ),
                },
            ],
        },
    )


def test_response_composer_keeps_bullets_and_table_for_grouped_answer() -> None:
    """Grouped multi-row answers still render bullets and the key-data table.

    Guards against over-suppression of the #275 fix: only ungrouped answers
    drop the metric bullet and table.
    """
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
            datasets_used=("Retail Operations",),
            dataset_tables_used=("orders",),
            metric_kind=schema.MetricKind.MONEY,
            metric_label="total revenue",
            time_range="January 2026",
            filters=(),
            caveats=(),
            group_by_label="region",
        )
    )

    assert "- North: $1,200.00" in response.text
    assert "- South: $850.00" in response.text
    assert "table" in {block["type"] for block in response.blocks}


def test_response_composer_numbers_ranked_plain_text_and_slack_table() -> None:
    response = response_composer.compose_final_response(
        contracts.AnswerDraft(
            summary=(
                "Total revenue in January 2026 was $2,050.00 across ranked regions."
            ),
            key_data=pd.DataFrame(
                {
                    "dimension_value": ("North", "South"),
                    "metric_value": (1200.0, 850.0),
                }
            ),
            datasets_used=("Retail Operations",),
            dataset_tables_used=("orders",),
            metric_kind=schema.MetricKind.MONEY,
            metric_label="total revenue",
            time_range="January 2026",
            filters=(),
            caveats=(),
            group_by_label="region",
            rank=contracts.RankSpec(
                result_limit=2,
                sort_direction=contracts.SortDirection.DESC,
            ),
        )
    )

    assert "1. North: $1,200.00" in response.text
    assert "2. South: $850.00" in response.text
    table_block = response.blocks[2]
    assert table_block["type"] == "table"
    rows = typing.cast(list[list[dict[str, str]]], table_block["rows"])
    assert rows[0] == [
        {"type": "raw_text", "text": "#"},
        {"type": "raw_text", "text": "Region"},
        {"type": "raw_text", "text": "Total Revenue"},
    ]
    assert rows[1] == [
        {"type": "raw_text", "text": "1"},
        {"type": "raw_text", "text": "North"},
        {"type": "raw_text", "text": "$1,200.00"},
    ]


def test_response_composer_builds_catalog_discovery_blocks_and_trust_summary() -> None:
    response = response_composer.compose_catalog_discovery_response(
        datasets=(
            contracts.CatalogDatasetSummary(
                dataset_name="Retail Operations",
                information_types=("revenue", "regional performance"),
                metric_labels=("customer count", "total revenue"),
                field_labels=("created date", "region"),
                example_questions=(
                    "What was total revenue by region in January 2026?",
                    "What was customer count by region in January 2026?",
                    "What was total revenue in the West region in January 2026?",
                ),
                example_sources=("curated", "generated", "generated"),
            ),
        ),
    )

    assert response.response_kind == contracts.ResponseKind.ANSWER
    assert "Retail Operations" in response.text
    assert "Prepared Data was not read." in response.text
    assert "orders" not in response.text
    assert response.blocks[0]["type"] == "section"
    assert response.blocks[1]["type"] == "context"
    assert "table" not in {block["type"] for block in response.blocks}
    assert response.trust_summary.datasets == ("Retail Operations",)
    assert response.non_answer is None


def test_response_composer_handles_zero_accessible_catalog_datasets_without_leaks() -> (
    None
):
    response = response_composer.compose_catalog_discovery_response(datasets=())

    assert response.response_kind == contracts.ResponseKind.ANSWER
    assert "no approved datasets are currently available" in response.text.lower()
    assert "restricted" not in response.text.lower()
    assert "0 dataset" not in response.text.lower()
    assert response.blocks == (
        {
            "type": "section",
            "text": {
                "type": "plain_text",
                "text": (
                    "No approved datasets are currently available for you to query."
                ),
            },
        },
        {
            "type": "context",
            "elements": [
                {
                    "type": "plain_text",
                    "text": (
                        "Trust Summary: Semantic Layer metadata used. Curated "
                        "Dataset names shown: none. Prepared Data was not read."
                    ),
                },
            ],
        },
    )


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
        _non_answer(contracts.NonAnswerReasonCode.UNSUPPORTED_INTENT),
        wording_provider=_SentinelWordingProvider(),
    )

    assert "I cannot answer safely because sentinel reason." in response.text
    assert "Next step: Sentinel step." in response.text
    assert response.trust_summary.limitations == ("Sentinel reason.",)


def test_response_composer_renders_non_answer_as_section_and_context_blocks() -> None:
    """Non-Answer blocks mirror the answer footer: body section + trust context.

    The answer path renders the body in a ``section`` and the Trust Summary in a
    small grey ``context`` block. The Non-Answer path must converge on that shape
    so the Trust Summary is not flattened into one inline section (issue #276).
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
        _non_answer(contracts.NonAnswerReasonCode.UNSUPPORTED_INTENT),
        wording_provider=_SentinelWordingProvider(),
    )

    assert response.blocks[0] == {
        "type": "section",
        "text": {
            "type": "plain_text",
            "text": (
                "I cannot answer safely because sentinel reason.\n\n"
                "Next step: Sentinel step."
            ),
        },
    }
    assert response.blocks[1] == {
        "type": "context",
        "elements": [
            {
                "type": "plain_text",
                "text": response_composer.render_trust_summary(
                    response.trust_summary
                ),
            },
        ],
    }


def test_response_composer_keeps_standalone_pronoun_i_capitalized() -> None:
    """A reason beginning with the pronoun ``I`` is not lowercased (issue #276).

    The leading-char lowercasing rule must skip the standalone pronoun so the
    body reads ``because I need …`` rather than ``because i need …``.
    """

    class _PronounWordingProvider:
        def render_wording(
            self,
            non_answer: contracts.NonAnswer,
        ) -> non_answer_catalog.NonAnswerWording:
            del non_answer
            return non_answer_catalog.NonAnswerWording(
                reason="I need a time period to answer.",
                next_step="Add a time period.",
            )

    response = response_composer.compose_non_answer_response(
        _non_answer(contracts.NonAnswerReasonCode.MISSING_TIME_SCOPE),
        wording_provider=_PronounWordingProvider(),
    )

    assert "because I need" in response.text
    assert "because i need" not in response.text


def test_response_composer_lowercases_non_pronoun_leading_word() -> None:
    """A non-pronoun leading word still lowercases (guards the ``I`` carve-out)."""

    class _NounWordingProvider:
        def render_wording(
            self,
            non_answer: contracts.NonAnswer,
        ) -> non_answer_catalog.NonAnswerWording:
            del non_answer
            return non_answer_catalog.NonAnswerWording(
                reason="Inventory data is not approved.",
                next_step="Pick an approved dataset.",
            )

    response = response_composer.compose_non_answer_response(
        _non_answer(contracts.NonAnswerReasonCode.NO_MATCHING_DATASET),
        wording_provider=_NounWordingProvider(),
    )

    assert "because inventory data" in response.text
    assert "because Inventory data" not in response.text


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
            datasets_used=("Retail Operations",),
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
    non_answer = _non_answer(contracts.NonAnswerReasonCode.UNSUPPORTED_INTENT)
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
        contracts.NonAnswerReasonCode.UNSUPPORTED_INTENT,
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
            "retail_ops",
            stage=contracts.NonAnswerStage.ACCESS_CONTROLLER,
        ),
        wording_provider=non_answer_catalog.StaticCatalogWording(),
    )

    assert "Curated Dataset: retail_ops." in response.text
    assert "Dataset Table:" not in response.text
    assert "Filters:" not in response.text

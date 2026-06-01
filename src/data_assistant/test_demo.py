from __future__ import annotations

import io

import data_assistant.demo as demo
import data_assistant.question_interpreter.question_frame_cases as question_frame_cases


def test_run_demo_returns_three_acknowledged_threaded_scenarios() -> None:
    results = demo.run_demo()

    assert [result.name for result in results] == [
        "happy_path",
        "customer_count_by_region",
        "safe_non_answer",
    ]
    assert [result.acknowledged for result in results] == [True, True, True]
    assert [result.response_thread_ts for result in results] == [
        result.request_ts for result in results
    ]


def test_run_demo_happy_path_shows_trust_summary_and_data_caveats() -> None:
    results = demo.run_demo()
    happy_path = results[0]

    assert "Trust Summary:" in happy_path.response_text
    assert "- Unknown: $500.00" in happy_path.response_text
    assert "1 row excluded because revenue was missing." in happy_path.response_text
    assert "1 row grouped under Unknown because region was missing." in (
        happy_path.response_text
    )


def test_run_demo_safe_non_answer_returns_clarification_response() -> None:
    results = demo.run_demo()
    non_answer = results[2]

    assert non_answer.request_text == "What was total revenue by region?"
    assert "I cannot answer safely yet" in non_answer.response_text
    assert "specify a time period or explicitly ask for all time" in (
        non_answer.response_text
    )
    assert "Next step: Ask which time period should be used, or confirm all time." in (
        non_answer.response_text
    )
    assert "Trust Summary:" in non_answer.response_text


def test_run_demo_customer_count_by_region_shows_count_trust_summary() -> None:
    results = demo.run_demo()
    customer_count = results[1]

    assert customer_count.request_text == (
        "What was customer count by customer region in January 2026?"
    )
    assert "Customer count in 2026-01-01 through 2026-01-31 was 5" in (
        customer_count.response_text
    )
    assert "- North: 2" in customer_count.response_text
    assert "- East: 1" in customer_count.response_text
    assert "- South: 1" in customer_count.response_text
    assert "- Unknown: 1" in customer_count.response_text
    assert "$" not in customer_count.response_text
    assert "Dataset Table: customers." in customer_count.response_text
    assert "Time range: 2026-01-01 through 2026-01-31." in (
        customer_count.response_text
    )


def test_main_prints_both_slack_like_demo_scenarios() -> None:
    stdout = io.StringIO()

    exit_code = demo.main(stdout=stdout)

    rendered = stdout.getvalue()
    assert exit_code == 0
    assert "Slack-like happy path request:" in rendered
    assert "Slack Acknowledgement: 200 OK" in rendered
    assert "threaded Final Response:" in rendered
    assert "Slack-like Non-Answer request:" in rendered
    assert "threaded Non-Answer Response:" in rendered


def test_demo_provider_replays_shared_question_frame_cases() -> None:
    provider = demo.build_demo_question_interpreter_provider()

    proposals_by_question = {
        case.question: provider.propose_question_frame(
            question=case.question,
            semantic_layer_context={},
        )
        for case in question_frame_cases.SHARED_QUESTION_FRAME_CASES
    }

    assert proposals_by_question == {
        case.question: case.expected
        for case in question_frame_cases.SHARED_QUESTION_FRAME_CASES
    }

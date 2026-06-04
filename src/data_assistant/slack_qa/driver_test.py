"""Tests for the Slack QA driver's pure parts.

The driver's ``main`` is near-untested by design (live Slack + live OpenAI,
like the ``live_eval`` mains). This file covers pure parsing, argument,
Known QA Issue preflight, and thread-target resolution behavior with no Slack
and no OpenAI.
"""

from __future__ import annotations

import collections.abc
import pathlib
import typing

import pytest

import data_assistant.assistant_thread_pointer as assistant_thread_pointer
import data_assistant.known_qa_issues as known_qa_issues
import data_assistant.slack_qa.driver as slack_qa_driver
import data_assistant.workflow.contracts as contracts


def test_parse_args_accepts_allow_unidentified_cases_flag() -> None:
    args = slack_qa_driver.build_arg_parser().parse_args(["--allow-unidentified-cases"])

    assert args.allow_unidentified_cases is True


def test_parse_args_accepts_known_issue_flags() -> None:
    args = slack_qa_driver.build_arg_parser().parse_args(
        [
            "--known-issues-path",
            "docs/custom.known-issues.json",
            "--skip-known-issue-prune",
        ]
    )

    assert args.known_issues_path == pathlib.Path("docs/custom.known-issues.json")
    assert args.skip_known_issue_prune is True


def test_parse_args_accepts_review_run_mode_flags() -> None:
    args = slack_qa_driver.build_arg_parser().parse_args(
        ["--interactive", "--skip-known-issues"]
    )

    assert args.interactive is True
    assert args.skip_known_issues is True


@pytest.mark.parametrize(
    (
        "channel",
        "thread_ts",
        "pointer",
        "expected",
    ),
    [
        pytest.param(
            "Cexplicit",
            "1.1",
            ("Cpointer", "9.9"),
            ("Cexplicit", "1.1"),
            id="explicit-args-win",
        ),
        pytest.param(
            None,
            None,
            ("Cpointer", "9.9"),
            ("Cpointer", "9.9"),
            id="fallback-to-pointer",
        ),
        pytest.param(
            "Cexplicit",
            None,
            ("Cpointer", "9.9"),
            ("Cexplicit", "9.9"),
            id="partial-args-fill-from-pointer",
        ),
        pytest.param(
            None,
            None,
            None,
            "No assistant thread found",
            id="missing-args-and-pointer",
        ),
        pytest.param(
            "Cexplicit",
            None,
            None,
            "No assistant thread found",
            id="partial-args-without-pointer",
        ),
    ],
)
def test_resolve_thread_target(
    tmp_path: pathlib.Path,
    channel: str | None,
    thread_ts: str | None,
    pointer: tuple[str, str] | None,
    expected: tuple[str, str] | str,
) -> None:
    pointer_path = tmp_path / "last_assistant_thread.json"
    if pointer is not None:
        assistant_thread_pointer.write_latest(*pointer, path=pointer_path)

    target = slack_qa_driver.resolve_thread_target(
        channel=channel,
        thread_ts=thread_ts,
        pointer_path=pointer_path,
    )

    if isinstance(expected, str):
        assert isinstance(target, str)
        assert expected in target
    else:
        assert target == expected


def test_replay_cases_passes_case_id_to_adapter_and_posts_blocks() -> None:
    seen_calls: list[tuple[str, str | None]] = []
    seen_contexts: list[slack_qa_driver.QAReviewContext | None] = []
    posted_messages: list[dict[str, object]] = []
    pauses: list[str] = []

    class FakeAdapter:
        def answer_and_render(
            self,
            *,
            text: str,
            user: str,
            qa_case_id: str | None = None,
            qa_review_context: slack_qa_driver.QAReviewContext | None = None,
            set_status: contracts.ProgressSink,
        ) -> tuple[str, contracts.FinalResponse, tuple[contracts.SlackBlock, ...]]:
            del user
            set_status("ignored")
            seen_calls.append((text, qa_case_id))
            seen_contexts.append(qa_review_context)
            return (
                "interaction-1",
                contracts.FinalResponse(
                    text=f"Answer for {text}",
                    trust_summary=contracts.TrustSummary(
                        datasets=("Retail Operations",)
                    ),
                    response_kind=contracts.ResponseKind.ANSWER,
                    blocks=(),
                ),
                (
                    {
                        "type": "section",
                        "text": {"type": "mrkdwn", "text": f"Answer for {text}"},
                    },
                ),
            )

    def post_message(**payload: object) -> None:
        posted_messages.append(payload)

    def pause(prompt: str) -> str:
        pauses.append(prompt)
        return ""

    slack_qa_driver.replay_cases(
        cases=[
            slack_qa_driver.QACase(
                id="orders-net-revenue-by-store-region-q1-2026",
                question="What was total revenue by region in January 2026?",
            )
        ],
        adapter=typing.cast("typing.Any", FakeAdapter()),
        channel="C123",
        thread_ts="1710000000.654321",
        post_message=post_message,
        pause=pause,
        battery_path="docs/qa-retail-questions.md",
        known_issues_by_case_id={},
        record_error=_discard_record_error,
    )

    assert seen_calls == [
        (
            "What was total revenue by region in January 2026?",
            "orders-net-revenue-by-store-region-q1-2026",
        )
    ]
    assert seen_contexts == [
        slack_qa_driver.QAReviewContext(
            battery_path="docs/qa-retail-questions.md",
            qa_case_id="orders-net-revenue-by-store-region-q1-2026",
            known_issues=(),
            position=1,
            total=1,
            note_saved=False,
        )
    ]
    assert posted_messages == [
        {
            "channel": "C123",
            "thread_ts": "1710000000.654321",
            "text": slack_qa_driver.QA_REVIEW_START_MARKER,
        },
        {
            "channel": "C123",
            "thread_ts": "1710000000.654321",
            "text": "Answer for What was total revenue by region in January 2026?",
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": (
                            "Answer for What was total revenue by region in "
                            "January 2026?"
                        ),
                    },
                }
            ],
        },
    ]
    assert pauses == ["  posted. Press Enter for the next question... "]


def test_replay_cases_default_mode_does_not_pause() -> None:
    pauses: list[str] = []

    class FakeAdapter:
        def answer_and_render(
            self,
            *,
            text: str,
            user: str,
            qa_case_id: str | None = None,
            qa_review_context: slack_qa_driver.QAReviewContext | None = None,
            set_status: contracts.ProgressSink,
        ) -> tuple[str, contracts.FinalResponse, tuple[contracts.SlackBlock, ...]]:
            del text, user, qa_case_id, qa_review_context
            set_status("ignored")
            return (
                "interaction-1",
                contracts.FinalResponse(
                    text="Answer",
                    trust_summary=contracts.TrustSummary(),
                    response_kind=contracts.ResponseKind.ANSWER,
                    blocks=(),
                ),
                (),
            )

    summary = slack_qa_driver.replay_cases(
        cases=[_case("case-a")],
        adapter=typing.cast("typing.Any", FakeAdapter()),
        channel="C123",
        thread_ts="1710000000.654321",
        post_message=_discard_post_message,
        pause=lambda prompt: pauses.append(prompt) or "",
        interactive=False,
        battery_path="docs/qa-retail-questions.md",
        known_issues_by_case_id={},
        record_error=_discard_record_error,
    )

    assert pauses == []
    assert summary.posted_count == 1
    assert summary.fallback_error_count == 0


def test_replay_cases_skip_known_issues_filters_after_preflight() -> None:
    seen_case_ids: list[str | None] = []

    class FakeAdapter:
        def answer_and_render(
            self,
            *,
            text: str,
            user: str,
            qa_case_id: str | None = None,
            qa_review_context: slack_qa_driver.QAReviewContext | None = None,
            set_status: contracts.ProgressSink,
        ) -> tuple[str, contracts.FinalResponse, tuple[contracts.SlackBlock, ...]]:
            del text, user, qa_review_context
            set_status("ignored")
            seen_case_ids.append(qa_case_id)
            return (
                "interaction-1",
                contracts.FinalResponse(
                    text="Answer",
                    trust_summary=contracts.TrustSummary(),
                    response_kind=contracts.ResponseKind.ANSWER,
                    blocks=(),
                ),
                (),
            )

    summary = slack_qa_driver.replay_cases(
        cases=[_case("case-a"), _case("case-b")],
        adapter=typing.cast("typing.Any", FakeAdapter()),
        channel="C123",
        thread_ts="1710000000.654321",
        post_message=_discard_post_message,
        pause=lambda _prompt: "",
        interactive=False,
        battery_path="docs/qa-retail-questions.md",
        known_issues_by_case_id={
            "case-a": [
                known_qa_issues.KnownQAIssue(
                    issue_number=166,
                    flag_category="correctness",
                )
            ]
        },
        record_error=_discard_record_error,
        skip_known_issues=True,
    )

    assert seen_case_ids == ["case-b"]
    assert summary.posted_count == 1
    assert summary.skipped_known_issue_count == 1


def test_replay_cases_posts_start_marker_and_summary(
    capsys: pytest.CaptureFixture[str],
) -> None:
    posted_messages: list[dict[str, object]] = []

    class FakeAdapter:
        def answer_and_render(
            self,
            *,
            text: str,
            user: str,
            qa_case_id: str | None = None,
            qa_review_context: slack_qa_driver.QAReviewContext | None = None,
            set_status: contracts.ProgressSink,
        ) -> tuple[str, contracts.FinalResponse, tuple[contracts.SlackBlock, ...]]:
            del text, user, qa_case_id, qa_review_context
            set_status("ignored")
            return (
                "interaction-1",
                contracts.FinalResponse(
                    text="Answer",
                    trust_summary=contracts.TrustSummary(),
                    response_kind=contracts.ResponseKind.ANSWER,
                    blocks=(),
                ),
                (),
            )

    summary = slack_qa_driver.replay_cases(
        cases=[_case("case-a"), _case("case-b")],
        adapter=typing.cast("typing.Any", FakeAdapter()),
        channel="C123",
        thread_ts="1710000000.654321",
        post_message=_record_post_message(posted_messages),
        pause=lambda _prompt: "",
        interactive=False,
        battery_path="docs/qa-retail-questions.md",
        known_issues_by_case_id={},
        record_error=_discard_record_error,
        preflight_pruned_count=3,
    )

    assert posted_messages[0] == {
        "channel": "C123",
        "thread_ts": "1710000000.654321",
        "text": slack_qa_driver.QA_REVIEW_START_MARKER,
    }
    assert summary.posted_count == 2
    output = capsys.readouterr().out
    assert "posted=2" in output
    assert "skipped_known_issues=0" in output
    assert "pruned=3" in output
    assert "fallback_errors=0" in output


def test_replay_cases_posts_runtime_fallback_continues_and_records_error() -> None:
    posted_messages: list[dict[str, object]] = []
    recorded_errors: list[dict[str, object]] = []

    class FakeAdapter:
        def answer_and_render(
            self,
            *,
            text: str,
            user: str,
            qa_case_id: str | None = None,
            qa_review_context: slack_qa_driver.QAReviewContext | None = None,
            set_status: contracts.ProgressSink,
        ) -> tuple[str, contracts.FinalResponse, tuple[contracts.SlackBlock, ...]]:
            del user, qa_review_context
            set_status("ignored")
            if qa_case_id == "case-a":
                raise RuntimeError("boom")
            return (
                "interaction-2",
                contracts.FinalResponse(
                    text=f"Answer for {text}",
                    trust_summary=contracts.TrustSummary(),
                    response_kind=contracts.ResponseKind.ANSWER,
                    blocks=(),
                ),
                (),
            )

    summary = slack_qa_driver.replay_cases(
        cases=[_case("case-a"), _case("case-b")],
        adapter=typing.cast("typing.Any", FakeAdapter()),
        channel="C123",
        thread_ts="1710000000.654321",
        post_message=_record_post_message(posted_messages),
        pause=lambda _prompt: "",
        interactive=False,
        battery_path="docs/qa-retail-questions.md",
        known_issues_by_case_id={
            "case-a": [
                known_qa_issues.KnownQAIssue(
                    issue_number=166,
                    flag_category="correctness",
                )
            ]
        },
        record_error=_record_error_call(recorded_errors),
    )

    assert posted_messages[0]["text"] == slack_qa_driver.QA_REVIEW_START_MARKER
    assert posted_messages[1]["text"] == slack_qa_driver.RUNTIME_FALLBACK_MESSAGE
    assert posted_messages[2]["text"] == "Answer for Question?"
    assert len(recorded_errors) == 1
    assert recorded_errors[0]["question"] == "Question?"
    assert recorded_errors[0]["user"] == "qa_driver"
    assert isinstance(recorded_errors[0]["error"], RuntimeError)
    assert recorded_errors[0]["qa_review_context"] == slack_qa_driver.QAReviewContext(
        battery_path="docs/qa-retail-questions.md",
        qa_case_id="case-a",
        known_issues=(
            known_qa_issues.KnownQAIssue(
                issue_number=166,
                flag_category="correctness",
            ),
        ),
        position=1,
        total=2,
        note_saved=False,
    )
    assert summary.posted_count == 1
    assert summary.fallback_error_count == 1


def _discard_post_message(**_payload: object) -> None:
    return None


def _discard_record_error(**_kwargs: object) -> None:
    return None


def _record_post_message(
    posted_messages: list[dict[str, object]],
) -> collections.abc.Callable[..., None]:
    def post_message(**payload: object) -> None:
        posted_messages.append(dict(payload))

    return post_message


def _record_error_call(
    recorded_errors: list[dict[str, object]],
) -> collections.abc.Callable[..., None]:
    def record_error(**kwargs: object) -> None:
        recorded_errors.append(dict(kwargs))

    return record_error


def _case(case_id: str, *, question: str = "Question?") -> slack_qa_driver.QACase:
    return slack_qa_driver.QACase(id=case_id, question=question)

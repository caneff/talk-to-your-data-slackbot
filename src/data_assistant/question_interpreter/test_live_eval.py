import io

import pytest

import data_assistant.question_interpreter.live_eval as live_eval
from data_assistant.question_interpreter import (
    live_provider_proposal_eval,
    provider_proposal_eval,
)


def test_live_eval_wrapper_reexports_provider_proposal_harness() -> None:
    assert live_eval.LiveEvalCase is provider_proposal_eval.ProviderProposalEvalCase
    assert (
        live_eval.run_live_question_interpreter_eval
        is provider_proposal_eval.run_provider_proposal_eval
    )
    assert (
        live_eval.compare_question_frame_meaning
        is provider_proposal_eval.compare_provider_proposal_meaning
    )


def test_live_eval_main_uses_live_provider_proposal_entrypoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[object, ...]] = []

    def fake_main(*args: object, **kwargs: object) -> int:
        calls.append(args + (kwargs,))
        return 0

    monkeypatch.setattr(live_provider_proposal_eval, "main", fake_main)

    exit_code = live_eval.main(stdout=io.StringIO(), stderr=io.StringIO(), environ={})

    assert exit_code == 0
    assert len(calls) == 1

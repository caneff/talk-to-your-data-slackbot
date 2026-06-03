import io
import pathlib
import types

import pytest

import data_assistant.semantic_layer.loader as semantic_layer_loader
import data_assistant.semantic_layer.testing_support as semantic_layer_testing
from data_assistant.question_interpreter import (
    live_provider_proposal_eval,
    provider_proposal_eval,
)


class _StubProvider:
    def propose_question_frame(
        self, *, question: str, semantic_layer_context: dict[str, object]
    ) -> provider_proposal_eval.ProviderResult:  # noqa: E501
        del question, semantic_layer_context
        raise AssertionError("runner should be stubbed")


def _build_stub_provider(environ: object) -> _StubProvider:
    del environ
    return _StubProvider()


def test_main_builds_provider_and_delegates_to_pure_eval(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: pathlib.Path,
) -> None:
    calls: list[types.SimpleNamespace] = []
    semantic_layer = semantic_layer_testing.semantic_layer_with_table()

    def fake_run_provider_proposal_eval(
        **kwargs: object,
    ) -> provider_proposal_eval.ProviderProposalEvalReport:
        calls.append(types.SimpleNamespace(**kwargs))
        return provider_proposal_eval.ProviderProposalEvalReport(
            total=0,
            passes=(),
            failures=(),
        )

    monkeypatch.setattr(
        live_provider_proposal_eval.question_interpreter,
        "build_openai_question_interpreter_provider",
        _build_stub_provider,
    )
    monkeypatch.setattr(
        live_provider_proposal_eval.semantic_layer_loader,
        "load_semantic_layer",
        lambda path=semantic_layer_loader.DEFAULT_SEMANTIC_LAYER_PATH: semantic_layer,
    )
    monkeypatch.setattr(
        live_provider_proposal_eval.provider_proposal_eval,
        "run_provider_proposal_eval",
        fake_run_provider_proposal_eval,
    )
    monkeypatch.chdir(tmp_path)

    exit_code = live_provider_proposal_eval.main(
        stdout=io.StringIO(),
        stderr=io.StringIO(),
        environ={},
    )

    assert exit_code == 0
    assert len(calls) == 1
    assert isinstance(calls[0].provider, _StubProvider)
    assert calls[0].semantic_layer is semantic_layer

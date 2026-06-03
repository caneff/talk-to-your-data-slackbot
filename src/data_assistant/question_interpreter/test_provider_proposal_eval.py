import pathlib

import data_assistant.question_interpreter.provider_proposal_cases as proposal_cases
import data_assistant.question_interpreter.provider_proposal_eval as proposal_eval
import data_assistant.question_interpreter.test_support as test_support
import data_assistant.semantic_layer.testing_support as semantic_layer_testing


class _PassingProvider:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

    def propose_question_frame(
        self,
        *,
        question: str,
        semantic_layer_context: dict[str, object],
    ) -> proposal_eval.ProviderResult:
        self.calls.append((question, semantic_layer_context))
        return test_support.question_frame_proposal()


def test_run_provider_proposal_eval_uses_injected_provider() -> None:
    provider = _PassingProvider()
    semantic_layer = semantic_layer_testing.semantic_layer_with_table()
    case = proposal_eval.ProviderProposalEvalCase(
        name="canonical_question",
        question="What was total revenue by region in January 2026?",
        expected=test_support.question_frame_proposal(),
    )

    report = proposal_eval.run_provider_proposal_eval(
        provider=provider,
        semantic_layer=semantic_layer,
        cases=(case,),
        sample_count=1,
    )

    assert report.total == 1
    assert report.passed == 1
    assert report.failed == 0
    assert [question for question, _ in provider.calls] == [case.question]


def test_default_cases_come_from_shared_provider_proposal_cases() -> None:
    assert (
        tuple(
            proposal_eval.ProviderProposalEvalCase(
                name=case.name,
                question=case.question,
                expected=case.expected,
                enabled=case.enabled,
                deferred=case.deferred,
            )
            for case in proposal_cases.SHARED_PROVIDER_PROPOSAL_CASES
        )
        == proposal_eval.DEFAULT_CASES
    )


def test_provider_proposal_cases_source_uses_provider_proposal_constructor() -> None:
    source = pathlib.Path(proposal_cases.__file__).read_text(encoding="utf-8")

    assert "SharedProviderProposalCase(" in source
    assert "SharedQuestionFrameCase(" not in source

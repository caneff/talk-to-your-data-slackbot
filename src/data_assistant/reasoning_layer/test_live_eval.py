import collections.abc
import io
import pathlib

import pytest

import data_assistant.reasoning_layer as reasoning_layer
import data_assistant.reasoning_layer.live_eval as live_eval
import data_assistant.reasoning_layer.narrative_cases as narrative_cases


def _fake_provider(
    proposal: reasoning_layer.NarrativeProposal | reasoning_layer.ProviderFailure,
) -> reasoning_layer.ReasoningProvider:
    class FakeProvider:
        def propose_narrative(
            self,
            *,
            result_shape: dict[str, object],
        ) -> reasoning_layer.NarrativeProposal | reasoning_layer.ProviderFailure:
            del result_shape
            return proposal

    return FakeProvider()


# --- comparator: grounded property ---


def test_comparator_passes_grounded_filled_proposal_with_values() -> None:
    proposal = reasoning_layer.NarrativeProposal(
        summary=(
            "{metric} in {time_range} totaled {metric_total}, led by "
            "{top_dimension} at {top_value}."
        )
    )
    slot_values = reasoning_layer.compute_slot_values(
        narrative_cases.prepared_revenue_by_region()
    )

    reasons = live_eval.compare_grounding(
        proposal=proposal,
        expectation=narrative_cases.GroundingExpectation(
            required_slots=("{top_dimension}",),
        ),
        slot_values=slot_values,
    )

    assert reasons == ()


def test_comparator_reports_ungrounded_digit() -> None:
    proposal = reasoning_layer.NarrativeProposal(summary="West led by 6%.")
    slot_values = reasoning_layer.compute_slot_values(
        narrative_cases.prepared_revenue_by_region()
    )

    reasons = live_eval.compare_grounding(
        proposal=proposal,
        expectation=narrative_cases.GroundingExpectation(),
        slot_values=slot_values,
    )

    assert "proposal is not grounded: prose contains a digit" in reasons


def test_comparator_reports_unfillable_unknown_slot() -> None:
    proposal = reasoning_layer.NarrativeProposal(summary="{metric} led by {region}.")
    slot_values = reasoning_layer.compute_slot_values(
        narrative_cases.prepared_revenue_by_region()
    )

    reasons = live_eval.compare_grounding(
        proposal=proposal,
        expectation=narrative_cases.GroundingExpectation(),
        slot_values=slot_values,
    )

    assert "proposal is not fillable: references an unknown slot" in reasons


def test_comparator_reports_missing_required_slot_token() -> None:
    proposal = reasoning_layer.NarrativeProposal(
        summary="{metric} in {time_range} totaled {metric_total}."
    )
    slot_values = reasoning_layer.compute_slot_values(
        narrative_cases.prepared_revenue_by_region()
    )

    reasons = live_eval.compare_grounding(
        proposal=proposal,
        expectation=narrative_cases.GroundingExpectation(
            required_slots=("{top_dimension}",),
        ),
        slot_values=slot_values,
    )

    assert "required slot {top_dimension} missing from proposal summary" in reasons


def test_comparator_reports_value_string_absent_from_filled_summary() -> None:
    proposal = reasoning_layer.NarrativeProposal(summary="{metric} in {time_range}.")
    slot_values = reasoning_layer.compute_slot_values(
        narrative_cases.prepared_revenue_by_region()
    )

    reasons = live_eval.compare_grounding(
        proposal=proposal,
        expectation=narrative_cases.GroundingExpectation(),
        slot_values=slot_values,
    )

    assert "$5,150.00" in slot_values["metric_total"]  # type: ignore[operator]
    assert reasons == (
        "computed value $5,150.00 absent from filled summary",
        "computed value $1,600.00 absent from filled summary",
    )


def test_comparator_reports_provider_failure_when_not_degradable() -> None:
    slot_values = reasoning_layer.compute_slot_values(
        narrative_cases.prepared_revenue_by_region()
    )

    reasons = live_eval.compare_grounding(
        proposal=reasoning_layer.ProviderFailure(reason="offline"),
        expectation=narrative_cases.GroundingExpectation(),
        slot_values=slot_values,
    )

    assert reasons == ("provider failure: offline",)


# --- degrade-guarantee tests via draft_narrative (the hard guarantee) ---


def test_degrade_guarantee_digit_proposal_falls_to_template() -> None:
    prepared_data = narrative_cases.prepared_revenue_by_region()
    provider = _fake_provider(
        reasoning_layer.NarrativeProposal(
            summary="{metric} in {time_range} jumped 6% over the prior period."
        )
    )

    answer_draft = reasoning_layer.draft_narrative(prepared_data, provider=provider)
    deterministic = reasoning_layer.draft_answer(prepared_data)

    assert answer_draft.summary == deterministic.summary
    assert reasoning_layer.WITHHELD_WORDING_CAVEAT in answer_draft.caveats


def test_degrade_guarantee_unknown_slot_proposal_falls_to_template() -> None:
    prepared_data = narrative_cases.prepared_revenue_by_region()
    provider = _fake_provider(
        reasoning_layer.NarrativeProposal(
            summary="{metric} in {time_range} led by {region}."
        )
    )

    answer_draft = reasoning_layer.draft_narrative(prepared_data, provider=provider)
    deterministic = reasoning_layer.draft_answer(prepared_data)

    assert answer_draft.summary == deterministic.summary
    assert reasoning_layer.WITHHELD_WORDING_CAVEAT in answer_draft.caveats


def test_degrade_guarantee_stray_brace_proposal_does_not_raise() -> None:
    prepared_data = narrative_cases.prepared_revenue_by_region()
    provider = _fake_provider(
        reasoning_layer.NarrativeProposal(
            summary="{metric} in {time_range} led by {top."
        )
    )

    answer_draft = reasoning_layer.draft_narrative(prepared_data, provider=provider)
    deterministic = reasoning_layer.draft_answer(prepared_data)

    assert answer_draft.summary == deterministic.summary
    assert reasoning_layer.WITHHELD_WORDING_CAVEAT in answer_draft.caveats


# --- runner / exit-code logic ---


def test_run_eval_reports_all_failures_without_fail_fast() -> None:
    class FakeProvider:
        def __init__(self) -> None:
            self.calls = 0

        def propose_narrative(
            self,
            *,
            result_shape: dict[str, object],
        ) -> reasoning_layer.NarrativeProposal | reasoning_layer.ProviderFailure:
            del result_shape
            self.calls += 1
            return reasoning_layer.NarrativeProposal(
                summary="{metric} in {time_range} totaled {metric_total}, led by "
                "{top_dimension} at {top_value}."
            )

    provider = FakeProvider()
    cases = (
        narrative_cases.SharedNarrativeCase(
            name="passing",
            prepared_data=narrative_cases.prepared_revenue_by_region(),
            expectation=narrative_cases.GroundingExpectation(
                required_slots=("{top_dimension}",),
            ),
        ),
        narrative_cases.SharedNarrativeCase(
            name="failing",
            prepared_data=narrative_cases.prepared_revenue_by_region(),
            expectation=narrative_cases.GroundingExpectation(
                required_slots=("{missing_slot}",),
            ),
        ),
    )

    report = live_eval.run_live_reasoning_eval(provider=provider, cases=cases)

    assert report.total == 2
    assert report.passed == 1
    assert report.failed == 1
    assert report.passes[0].case_name == "passing"
    assert report.passes[0].pass_count == 3
    assert report.passes[0].sample_count == 3
    assert report.failures[0].case_name == "failing"
    assert report.failures[0].reasons == (
        "sample 1: required slot {missing_slot} missing from proposal summary",
        "sample 2: required slot {missing_slot} missing from proposal summary",
        "sample 3: required slot {missing_slot} missing from proposal summary",
    )
    assert provider.calls == 6


def test_run_eval_requires_all_samples_to_pass_for_case_pass() -> None:
    class FakeProvider:
        def __init__(self) -> None:
            self.calls = 0
            self.proposals = (
                reasoning_layer.NarrativeProposal(
                    summary="{metric} totaled {metric_total}, led by "
                    "{top_dimension} at {top_value}."
                ),
                reasoning_layer.NarrativeProposal(summary="West led by 6%."),
                reasoning_layer.NarrativeProposal(
                    summary="{metric} totaled {metric_total}, led by "
                    "{top_dimension} at {top_value}."
                ),
            )

        def propose_narrative(
            self,
            *,
            result_shape: dict[str, object],
        ) -> reasoning_layer.NarrativeProposal | reasoning_layer.ProviderFailure:
            del result_shape
            proposal = self.proposals[self.calls]
            self.calls += 1
            return proposal

    provider = FakeProvider()
    cases = (
        narrative_cases.SharedNarrativeCase(
            name="flaky",
            prepared_data=narrative_cases.prepared_revenue_by_region(),
            expectation=narrative_cases.GroundingExpectation(),
        ),
    )

    report = live_eval.run_live_reasoning_eval(provider=provider, cases=cases)

    assert report.passed == 0
    assert report.failed == 1
    assert report.failures[0].pass_count == 2
    assert report.failures[0].sample_count == 3
    assert (
        "sample 2: proposal is not grounded: prose contains a digit"
        in report.failures[0].reasons
    )


def test_run_eval_skips_disabled_cases() -> None:
    provider = _fake_provider(reasoning_layer.NarrativeProposal(summary="West led."))
    cases = (
        narrative_cases.SharedNarrativeCase(
            name="disabled",
            prepared_data=narrative_cases.prepared_revenue_by_region(),
            expectation=narrative_cases.GroundingExpectation(),
            enabled=False,
        ),
    )

    report = live_eval.run_live_reasoning_eval(provider=provider, cases=cases)

    assert report.total == 0


def test_run_eval_rejects_non_positive_sample_count() -> None:
    provider = _fake_provider(reasoning_layer.NarrativeProposal(summary="x"))

    with pytest.raises(ValueError):
        live_eval.run_live_reasoning_eval(
            provider=provider,
            cases=(),
            sample_count=0,
        )


def test_default_cases_come_from_shared_narrative_cases() -> None:
    assert live_eval.DEFAULT_CASES is narrative_cases.SHARED_NARRATIVE_CASES
    assert len(live_eval.DEFAULT_CASES) == 3


# --- report writing ---


def test_write_report_hides_passed_case_details_by_default() -> None:
    stdout = io.StringIO()
    report = live_eval.LiveEvalReport(
        total=1,
        passes=(
            live_eval.LiveEvalPass(
                case_name="grouped",
                pass_count=3,
                sample_count=3,
            ),
        ),
        failures=(),
    )

    live_eval.write_live_eval_report(stdout=stdout, report=report)

    assert stdout.getvalue() == (
        "Total cases: 1\nPassed: 1\nFailed: 0\n[PASS] grouped (pass rate: 3/3)\n"
    )


def test_write_report_includes_failure_reasons() -> None:
    stdout = io.StringIO()
    report = live_eval.LiveEvalReport(
        total=1,
        passes=(),
        failures=(
            live_eval.LiveEvalFailure(
                case_name="failing",
                reasons=("sample 1: proposal is not grounded: prose contains a digit",),
                pass_count=0,
                sample_count=3,
            ),
        ),
    )

    live_eval.write_live_eval_report(stdout=stdout, report=report)

    output = stdout.getvalue()
    assert "Total cases: 1\nPassed: 0\nFailed: 1\n" in output
    assert "[FAIL] failing (pass rate: 0/3)" in output
    assert "proposal is not grounded: prose contains a digit" in output


# --- main: key-gated ---


def test_main_returns_one_and_prints_missing_api_key_error() -> None:
    stdout = io.StringIO()
    stderr = io.StringIO()

    exit_code = live_eval.main(stdout=stdout, stderr=stderr, environ={})

    assert exit_code == 1
    assert stdout.getvalue() == ""
    assert stderr.getvalue().strip() == (
        "Missing required OpenAI environment variables: OPENAI_API_KEY"
    )


def test_main_returns_zero_when_all_cases_pass(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: pathlib.Path,
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("OPENAI_API_KEY=dotenv-key\n", encoding="utf-8")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    def fake_build_provider(
        environ: collections.abc.Mapping[str, str],
    ) -> reasoning_layer.ReasoningProvider:
        assert environ["OPENAI_API_KEY"] == "dotenv-key"
        return _fake_provider(reasoning_layer.NarrativeProposal(summary="x"))

    def fake_run_eval(
        *,
        provider: reasoning_layer.ReasoningProvider,
        cases: collections.abc.Iterable[narrative_cases.SharedNarrativeCase] = (
            live_eval.DEFAULT_CASES
        ),
        sample_count: int = live_eval.DEFAULT_SAMPLE_COUNT,
    ) -> live_eval.LiveEvalReport:
        del provider, cases, sample_count
        return live_eval.LiveEvalReport(total=0, passes=(), failures=())

    monkeypatch.setattr(
        live_eval.reasoning_layer,
        "build_openai_reasoning_provider",
        fake_build_provider,
    )
    monkeypatch.setattr(live_eval, "run_live_reasoning_eval", fake_run_eval)

    exit_code = live_eval.main(
        stdout=io.StringIO(),
        stderr=io.StringIO(),
        env_file=env_file,
    )

    assert exit_code == 0


def test_main_returns_one_when_report_has_failures(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: pathlib.Path,
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("OPENAI_API_KEY=dotenv-key\n", encoding="utf-8")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    def fake_build_provider(
        environ: collections.abc.Mapping[str, str],
    ) -> reasoning_layer.ReasoningProvider:
        del environ
        return _fake_provider(reasoning_layer.NarrativeProposal(summary="x"))

    def fake_run_eval(
        *,
        provider: reasoning_layer.ReasoningProvider,
        cases: collections.abc.Iterable[narrative_cases.SharedNarrativeCase] = (
            live_eval.DEFAULT_CASES
        ),
        sample_count: int = live_eval.DEFAULT_SAMPLE_COUNT,
    ) -> live_eval.LiveEvalReport:
        del provider, cases, sample_count
        return live_eval.LiveEvalReport(
            total=1,
            passes=(),
            failures=(
                live_eval.LiveEvalFailure(
                    case_name="failing",
                    reasons=("sample 1: not grounded",),
                    pass_count=0,
                    sample_count=3,
                ),
            ),
        )

    monkeypatch.setattr(
        live_eval.reasoning_layer,
        "build_openai_reasoning_provider",
        fake_build_provider,
    )
    monkeypatch.setattr(live_eval, "run_live_reasoning_eval", fake_run_eval)

    exit_code = live_eval.main(
        stdout=io.StringIO(),
        stderr=io.StringIO(),
        env_file=env_file,
    )

    assert exit_code == 1

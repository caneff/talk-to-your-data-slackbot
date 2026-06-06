import dataclasses
import typing

import pytest

import data_assistant.openai_support as openai_support


class _StubConfigError(ValueError):
    """Stub component config error for parameterized parsing tests."""


@dataclasses.dataclass(frozen=True)
class _StubProposal:
    """Stub parsed proposal type for the generic parse runner."""

    value: str


@dataclasses.dataclass(frozen=True)
class _StubFailure:
    """Stub component-specific provider failure."""

    reason: str


def _stub_failure(reason: str) -> _StubFailure:
    return _StubFailure(reason=reason)


@dataclasses.dataclass(frozen=True)
class _StubFailureWithDiagnostic:
    """Stub component-specific provider failure with safe diagnostic class."""

    reason: str
    diagnostic_class: str


def _stub_failure_with_diagnostic(
    reason: str,
    diagnostic_class: str,
) -> _StubFailureWithDiagnostic:
    return _StubFailureWithDiagnostic(
        reason=reason,
        diagnostic_class=diagnostic_class,
    )


def test_require_api_key_raises_passed_error_class_with_exact_message() -> None:
    with pytest.raises(_StubConfigError) as error_info:
        openai_support.require_api_key({}, _StubConfigError)

    assert str(error_info.value) == (
        "Missing required OpenAI environment variables: OPENAI_API_KEY"
    )


def test_require_api_key_returns_key_when_present() -> None:
    assert (
        openai_support.require_api_key({"OPENAI_API_KEY": "k"}, _StubConfigError) == "k"
    )


def test_parse_timeout_seconds_defaults_to_fifteen() -> None:
    assert openai_support.parse_timeout_seconds({}, _StubConfigError) == 15.0


def test_parse_timeout_seconds_allows_override() -> None:
    assert (
        openai_support.parse_timeout_seconds(
            {"OPENAI_TIMEOUT_SECONDS": "42.5"}, _StubConfigError
        )
        == 42.5
    )


def test_parse_timeout_seconds_rejects_non_numeric_with_exact_message() -> None:
    with pytest.raises(_StubConfigError) as error_info:
        openai_support.parse_timeout_seconds(
            {"OPENAI_TIMEOUT_SECONDS": "soon"}, _StubConfigError
        )

    assert str(error_info.value) == "Invalid OPENAI_TIMEOUT_SECONDS: 'soon'"


def test_parse_max_retries_defaults_to_one() -> None:
    assert openai_support.parse_max_retries({}, _StubConfigError) == 1


def test_parse_max_retries_allows_override() -> None:
    assert (
        openai_support.parse_max_retries({"OPENAI_MAX_RETRIES": "3"}, _StubConfigError)
        == 3
    )


def test_parse_max_retries_rejects_non_numeric_with_exact_message() -> None:
    with pytest.raises(_StubConfigError) as error_info:
        openai_support.parse_max_retries(
            {"OPENAI_MAX_RETRIES": "lots"}, _StubConfigError
        )

    assert str(error_info.value) == "Invalid OPENAI_MAX_RETRIES: 'lots'"


def test_build_openai_client_passes_api_key_timeout_and_retries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_kwargs: dict[str, object] = {}

    class FakeOpenAI:
        def __init__(self, **kwargs: object) -> None:
            captured_kwargs.update(kwargs)

        responses = object()

    monkeypatch.setattr(openai_support, "OpenAI", FakeOpenAI)

    @dataclasses.dataclass(frozen=True)
    class _Config:
        api_key: str = "test-key"
        timeout_seconds: float = 42.5
        max_retries: int = 3

    openai_support.build_openai_client(_Config())

    assert captured_kwargs["api_key"] == "test-key"
    assert captured_kwargs["timeout"] == 42.5
    assert captured_kwargs["max_retries"] == 3


def test_extract_response_refusal_returns_refusal_text() -> None:
    class FakeRefusalContent:
        type = "refusal"
        refusal = "cannot comply"

    class FakeMessageOutput:
        type = "message"
        content = [FakeRefusalContent()]

    class FakeRefusalResponse:
        output = [FakeMessageOutput()]

    assert (
        openai_support.extract_response_refusal(FakeRefusalResponse())
        == "cannot comply"
    )


def test_extract_response_refusal_returns_none_without_refusal() -> None:
    class FakeResponse:
        output = ()

    assert openai_support.extract_response_refusal(FakeResponse()) is None


def _run_parse(
    response: object,
    *,
    parse_calls: list[dict[str, object]] | None = None,
    extra_parse_kwargs: dict[str, object] | None = None,
) -> _StubProposal | _StubFailure:
    class FakeResponsesClient:
        def parse(self, **kwargs: object) -> object:
            if parse_calls is not None:
                parse_calls.append(kwargs)
            return response

    class FakeOpenAIClient:
        responses = FakeResponsesClient()

    client = typing.cast(
        openai_support.OpenAIClient,
        FakeOpenAIClient(),
    )
    return openai_support.run_parse(
        client=client,
        model="gpt-test-mini",
        input_messages=[{"role": "user", "content": "{}"}],
        text_format=_StubProposal,
        failure_factory=_stub_failure,
        extra_parse_kwargs=extra_parse_kwargs,
    )


def test_run_parse_returns_parsed_output_on_happy_path() -> None:
    class FakeParsedResponse:
        output_parsed = _StubProposal(value="ok")

    result = _run_parse(FakeParsedResponse())

    assert result == _StubProposal(value="ok")


def test_run_parse_forwards_model_input_and_text_format() -> None:
    parse_calls: list[dict[str, object]] = []

    class FakeParsedResponse:
        output_parsed = _StubProposal(value="ok")

    _run_parse(FakeParsedResponse(), parse_calls=parse_calls)

    assert len(parse_calls) == 1
    assert parse_calls[0]["model"] == "gpt-test-mini"
    assert parse_calls[0]["text_format"] is _StubProposal
    assert parse_calls[0]["input"] == [{"role": "user", "content": "{}"}]


def test_run_parse_forwards_extra_parse_kwargs() -> None:
    parse_calls: list[dict[str, object]] = []

    class FakeParsedResponse:
        output_parsed = _StubProposal(value="ok")

    _run_parse(
        FakeParsedResponse(),
        parse_calls=parse_calls,
        extra_parse_kwargs={"temperature": 0},
    )

    assert parse_calls[0]["temperature"] == 0


def test_run_parse_omits_temperature_when_no_extra_kwargs() -> None:
    parse_calls: list[dict[str, object]] = []

    class FakeParsedResponse:
        output_parsed = _StubProposal(value="ok")

    _run_parse(FakeParsedResponse(), parse_calls=parse_calls)

    assert "temperature" not in parse_calls[0]


def test_run_parse_maps_refusal_to_failure_via_factory() -> None:
    class FakeRefusalContent:
        type = "refusal"
        refusal = "cannot comply"

    class FakeMessageOutput:
        type = "message"
        content = [FakeRefusalContent()]

    class FakeRefusalResponse:
        output_parsed = None
        output = [FakeMessageOutput()]

    result = _run_parse(FakeRefusalResponse())

    assert result == _StubFailure(reason="cannot comply")


def test_run_parse_maps_missing_output_to_failure_via_factory() -> None:
    class FakeMissingParsedResponse:
        output_parsed = None

    result = _run_parse(FakeMissingParsedResponse())

    assert result == _StubFailure(reason="OpenAI provider returned no parsed output")


def test_run_parse_maps_exception_to_failure_via_factory() -> None:
    class FailingResponsesClient:
        def parse(self, **kwargs: object) -> object:
            del kwargs
            raise RuntimeError("boom")

    class FakeOpenAIClient:
        responses = FailingResponsesClient()

    client = typing.cast(
        openai_support.OpenAIClient,
        FakeOpenAIClient(),
    )

    result = openai_support.run_parse(
        client=client,
        model="gpt-test-mini",
        input_messages=[{"role": "user", "content": "{}"}],
        text_format=_StubProposal,
        failure_factory=_stub_failure,
    )

    assert result == _StubFailure(reason="boom")


@pytest.mark.parametrize(
    ("exception_type_name", "expected_diagnostic_class"),
    (
        ("AuthenticationError", "provider_authentication_error"),
        ("PermissionDeniedError", "provider_permission_denied"),
        ("RateLimitError", "provider_rate_limit"),
        ("BadRequestError", "provider_bad_request"),
        ("APIConnectionError", "provider_connection_error"),
        ("APIStatusError", "provider_api_status_error"),
        ("APIError", "provider_api_error"),
        ("RuntimeError", "provider_exception"),
    ),
)
def test_run_parse_classifies_exception_type_to_safe_diagnostic_class(
    exception_type_name: str,
    expected_diagnostic_class: str,
) -> None:
    exception_type = type(exception_type_name, (Exception,), {})

    class FailingResponsesClient:
        def parse(self, **kwargs: object) -> object:
            del kwargs
            raise exception_type("boom")

    class FakeOpenAIClient:
        responses = FailingResponsesClient()

    client = typing.cast(
        openai_support.OpenAIClient,
        FakeOpenAIClient(),
    )

    result = openai_support.run_parse(
        client=client,
        model="gpt-test-mini",
        input_messages=[{"role": "user", "content": "{}"}],
        text_format=_StubProposal,
        failure_factory=_stub_failure,
        failure_with_diagnostic_factory=_stub_failure_with_diagnostic,
    )

    assert result == _StubFailureWithDiagnostic(
        reason="boom",
        diagnostic_class=expected_diagnostic_class,
    )


def test_developer_message_reads_prompt_file() -> None:
    message = openai_support.developer_message("reasoning_layer_developer.md")

    assert message["role"] == "developer"
    assert message["content"]

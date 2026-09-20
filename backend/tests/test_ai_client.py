"""Covers app/ai/client.py's provider selection and the two app/ai/llm.py
adapters. Uses fake API objects throughout - no real network calls, no
API key required to run this suite.
"""

from types import SimpleNamespace

import pytest

from app.ai import client as client_module
from app.ai.llm import AnthropicLlmClient, GroqLlmClient


@pytest.fixture(autouse=True)
def _clear_client_cache():
    """get_client() is @lru_cache(maxsize=1) - clear it before and after
    every test so one test's provider choice can't leak into the next.
    """
    client_module.get_client.cache_clear()
    yield
    client_module.get_client.cache_clear()


def test_get_client_raises_without_anthropic_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(client_module, "AI_PROVIDER", "anthropic")
    monkeypatch.setattr(client_module, "ANTHROPIC_API_KEY", None)
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        client_module.get_client()


def test_get_client_raises_without_groq_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(client_module, "AI_PROVIDER", "groq")
    monkeypatch.setattr(client_module, "GROQ_API_KEY", None)
    with pytest.raises(RuntimeError, match="GROQ_API_KEY"):
        client_module.get_client()


def test_get_client_raises_for_unknown_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(client_module, "AI_PROVIDER", "openai")
    with pytest.raises(RuntimeError, match="openai"):
        client_module.get_client()


def test_get_client_returns_anthropic_client_when_selected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(client_module, "AI_PROVIDER", "anthropic")
    monkeypatch.setattr(client_module, "ANTHROPIC_API_KEY", "sk-ant-fake")
    assert isinstance(client_module.get_client(), AnthropicLlmClient)


def test_get_client_returns_groq_client_when_selected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(client_module, "AI_PROVIDER", "groq")
    monkeypatch.setattr(client_module, "GROQ_API_KEY", "gsk-fake")
    assert isinstance(client_module.get_client(), GroqLlmClient)


def test_anthropic_llm_client_extracts_text_from_content_blocks() -> None:
    fake_response = SimpleNamespace(
        content=[
            SimpleNamespace(type="text", text="hello "),
            SimpleNamespace(type="text", text="world"),
        ]
    )
    calls = []

    class FakeMessages:
        def create(self, **kwargs):
            calls.append(kwargs)
            return fake_response

    fake_client = SimpleNamespace(messages=FakeMessages())
    llm = AnthropicLlmClient(fake_client, model="claude-test")

    result = llm.complete(system="sys", user_content="hi", max_tokens=50)

    assert result == "hello world"
    assert calls == [
        {
            "model": "claude-test",
            "max_tokens": 50,
            "system": "sys",
            "messages": [{"role": "user", "content": "hi"}],
        }
    ]


def test_groq_llm_client_extracts_message_content() -> None:
    fake_response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="hello from groq"))]
    )
    calls = []

    class FakeCompletions:
        def create(self, **kwargs):
            calls.append(kwargs)
            return fake_response

    fake_client = SimpleNamespace(chat=SimpleNamespace(completions=FakeCompletions()))
    llm = GroqLlmClient(fake_client, model="llama-test")

    result = llm.complete(system="sys", user_content="hi", max_tokens=50)

    assert result == "hello from groq"
    assert calls == [
        {
            "model": "llama-test",
            "max_tokens": 50,
            "messages": [
                {"role": "system", "content": "sys"},
                {"role": "user", "content": "hi"},
            ],
        }
    ]


@pytest.fixture()
def _reset_runtime_key():
    yield
    client_module.set_runtime_api_key(None)


def test_runtime_key_satisfies_missing_env_key(monkeypatch: pytest.MonkeyPatch, _reset_runtime_key) -> None:
    monkeypatch.setattr(client_module, "AI_PROVIDER", "groq")
    monkeypatch.setattr(client_module, "GROQ_API_KEY", None)
    assert not client_module.is_configured()

    client_module.set_runtime_api_key("  gsk-from-ui  ")

    assert client_module.is_configured()
    assert isinstance(client_module.get_client(), GroqLlmClient)


def test_runtime_key_overrides_env_key_and_rebuilds_client(monkeypatch: pytest.MonkeyPatch, _reset_runtime_key) -> None:
    monkeypatch.setattr(client_module, "AI_PROVIDER", "groq")
    monkeypatch.setattr(client_module, "GROQ_API_KEY", "gsk-env")
    first = client_module.get_client()

    client_module.set_runtime_api_key("gsk-ui")

    assert client_module.get_client() is not first  # cache dropped, rebuilt with the new key


def test_clearing_runtime_key_falls_back_to_env(monkeypatch: pytest.MonkeyPatch, _reset_runtime_key) -> None:
    monkeypatch.setattr(client_module, "AI_PROVIDER", "groq")
    monkeypatch.setattr(client_module, "GROQ_API_KEY", None)
    client_module.set_runtime_api_key("gsk-ui")
    client_module.set_runtime_api_key("   ")

    assert not client_module.is_configured()
    with pytest.raises(RuntimeError, match="GROQ_API_KEY"):
        client_module.get_client()


def test_shared_interpreter_picks_up_key_entered_after_first_failure(
    monkeypatch: pytest.MonkeyPatch, _reset_runtime_key
) -> None:
    from app.ai.requirement_interpreter import RequirementInterpreter

    monkeypatch.setattr(client_module, "AI_PROVIDER", "groq")
    monkeypatch.setattr(client_module, "GROQ_API_KEY", None)
    interpreter = RequirementInterpreter()
    with pytest.raises(RuntimeError):
        interpreter._get_client()

    client_module.set_runtime_api_key("gsk-ui")

    assert isinstance(interpreter._get_client(), GroqLlmClient)


def _status_error(sdk, error_name: str, status: int, message: str = "boom"):
    """Builds a real SDK status exception (they need an httpx response)."""
    import httpx

    response = httpx.Response(status, request=httpx.Request("POST", "http://test"))
    return getattr(sdk, error_name)(message, response=response, body=None)


@pytest.mark.parametrize(
    ("error_name", "status", "message", "expected_code"),
    [
        ("AuthenticationError", 401, "Invalid API Key", "ai_invalid_key"),
        ("PermissionDeniedError", 403, "forbidden", "ai_invalid_key"),
        ("RateLimitError", 429, "slow down", "ai_rate_limited"),
        ("NotFoundError", 404, "model_not_found", "ai_model_unavailable"),
        ("BadRequestError", 400, "The model `x` has been decommissioned", "ai_model_unavailable"),
        ("BadRequestError", 400, "malformed request", "ai_error"),
        ("InternalServerError", 500, "oops", "ai_error"),
    ],
)
def test_groq_adapter_translates_sdk_errors(error_name: str, status: int, message: str, expected_code: str) -> None:
    import groq

    from app.ai.errors import AiProviderError

    exc = _status_error(groq, error_name, status, message)
    fake = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **_: (_ for _ in ()).throw(exc)))
    )
    with pytest.raises(AiProviderError) as info:
        GroqLlmClient(fake, "m").complete(system="s", user_content="u", max_tokens=5)
    assert info.value.code == expected_code
    assert info.value.__cause__ is exc


def test_groq_adapter_translates_connection_error() -> None:
    import groq
    import httpx

    from app.ai.errors import AiProviderError

    exc = groq.APIConnectionError(request=httpx.Request("POST", "http://test"))
    fake = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **_: (_ for _ in ()).throw(exc)))
    )
    with pytest.raises(AiProviderError) as info:
        GroqLlmClient(fake, "m").complete(system="s", user_content="u", max_tokens=5)
    assert info.value.code == "ai_unreachable"


def test_anthropic_adapter_translates_sdk_errors() -> None:
    import anthropic

    from app.ai.errors import AiProviderError

    exc = _status_error(anthropic, "AuthenticationError", 401, "invalid x-api-key")
    fake = SimpleNamespace(messages=SimpleNamespace(create=lambda **_: (_ for _ in ()).throw(exc)))
    with pytest.raises(AiProviderError) as info:
        AnthropicLlmClient(fake, "m").complete(system="s", user_content="u", max_tokens=5)
    assert info.value.code == "ai_invalid_key"


@pytest.mark.parametrize("bad_key", ["gsk_věc", "gsk_ab cd", "gsk_	abc", "klíč"])
def test_runtime_key_rejects_non_ascii_or_inner_whitespace(bad_key: str, _reset_runtime_key) -> None:
    client_module.set_runtime_api_key("gsk-good")
    with pytest.raises(client_module.InvalidApiKeyError):
        client_module.set_runtime_api_key(bad_key)
    assert client_module._runtime_api_key == "gsk-good"  # previous key untouched


def test_invalid_key_error_reports_offending_character_and_position(_reset_runtime_key) -> None:
    with pytest.raises(client_module.InvalidApiKeyError) as info:
        client_module.set_runtime_api_key("gěsk")
    assert (info.value.position, info.value.char) == (2, "ě")
    assert "gěsk" not in str(info.value)  # never echo the key itself


def _capturing_groq_client(seen: dict) -> SimpleNamespace:
    def create(**kwargs):
        seen.update(kwargs)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))])

    return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))


def test_groq_reasoning_model_gets_low_effort_hidden_reasoning_and_headroom() -> None:
    seen: dict = {}
    GroqLlmClient(_capturing_groq_client(seen), "openai/gpt-oss-120b").complete(
        system="s", user_content="u", max_tokens=100
    )
    assert seen["reasoning_effort"] == "low"
    assert seen["include_reasoning"] is False
    assert seen["max_tokens"] > 100


def test_groq_non_reasoning_model_sends_no_reasoning_parameters() -> None:
    seen: dict = {}
    GroqLlmClient(_capturing_groq_client(seen), "llama-3.1-8b-instant").complete(
        system="s", user_content="u", max_tokens=100
    )
    assert "reasoning_effort" not in seen
    assert "include_reasoning" not in seen
    assert seen["max_tokens"] == 100

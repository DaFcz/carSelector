"""Covers app/ai/trace.py's log and the tracing both app/ai/llm.py
adapters do around every SDK call. Fake SDK objects only - no network.
"""

from types import SimpleNamespace

import groq
import httpx
import pytest

from app.ai import llm as llm_module
from app.ai.errors import AiProviderError
from app.ai.llm import AnthropicLlmClient, GroqLlmClient
from app.ai.trace import LlmTraceLog, llm_purpose


@pytest.fixture()
def log(monkeypatch: pytest.MonkeyPatch) -> LlmTraceLog:
    """A fresh log swapped in for the process-wide one."""
    fresh = LlmTraceLog(max_entries=3)
    monkeypatch.setattr(llm_module, "trace_log", fresh)
    return fresh


def _groq_client(create) -> GroqLlmClient:
    fake = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    return GroqLlmClient(fake, model="openai/gpt-oss-120b")


def test_groq_success_is_traced_with_request_reply_and_usage(log: LlmTraceLog) -> None:
    response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="ahoj"))],
        usage=SimpleNamespace(prompt_tokens=12, completion_tokens=34),
    )
    llm = _groq_client(lambda **kwargs: response)

    with llm_purpose("explanation"):
        assert llm.complete(system="sys", user_content="Škoda?", max_tokens=100) == "ahoj"

    [entry] = log.entries()
    assert entry.ok
    assert entry.provider == "groq"
    assert entry.model == "openai/gpt-oss-120b"
    assert entry.purpose == "explanation"
    assert entry.request["messages"][1] == {"role": "user", "content": "Škoda?"}
    assert entry.request["reasoning_effort"] == "low"  # the exact payload, extras included
    assert entry.reply_text == "ahoj"
    assert (entry.input_tokens, entry.output_tokens) == (12, 34)
    assert entry.duration_ms >= 0


def test_groq_api_error_is_traced_and_still_raised(log: LlmTraceLog) -> None:
    def create(**kwargs):
        response = httpx.Response(429, request=httpx.Request("POST", "https://api.groq.com/x"))
        raise groq.RateLimitError("slow down", response=response, body={"error": {"message": "slow down"}})

    with pytest.raises(AiProviderError) as excinfo:
        _groq_client(create).complete(system="s", user_content="u", max_tokens=10)

    assert excinfo.value.code == "ai_rate_limited"
    [entry] = log.entries()
    assert not entry.ok
    assert entry.error_code == "ai_rate_limited"
    assert entry.response == {"error": {"message": "slow down"}}
    assert entry.reply_text is None


def test_unexpected_exception_is_traced_and_reraised(log: LlmTraceLog) -> None:
    def create(**kwargs):
        raise UnicodeEncodeError("ascii", "ě", 0, 1, "bad header")

    with pytest.raises(UnicodeEncodeError):
        _groq_client(create).complete(system="s", user_content="u", max_tokens=10)

    assert log.entries()[0].error_code == "exception"


def test_anthropic_calls_are_traced_too(log: LlmTraceLog) -> None:
    response = SimpleNamespace(
        content=[SimpleNamespace(type="text", text="hi")],
        usage=SimpleNamespace(input_tokens=5, output_tokens=1),
    )
    fake = SimpleNamespace(messages=SimpleNamespace(create=lambda **kwargs: response))

    AnthropicLlmClient(fake, model="claude-test").complete(system="sys", user_content="u", max_tokens=10)

    [entry] = log.entries()
    assert entry.provider == "anthropic"
    assert entry.request["system"] == "sys"
    assert (entry.input_tokens, entry.output_tokens) == (5, 1)


def test_log_keeps_newest_entries_up_to_capacity_and_clears() -> None:
    log = LlmTraceLog(max_entries=2)
    for model in ("a", "b", "c"):
        log.record(
            started_at=None, provider="groq", model=model, request={}, response=None, reply_text="", duration_ms=0
        )

    assert [e.model for e in log.entries()] == ["c", "b"]
    version = log.version
    log.clear()
    assert log.entries() == []
    assert log.version > version


def test_zero_capacity_disables_tracing() -> None:
    log = LlmTraceLog(max_entries=0)
    assert not log.enabled
    assert (
        log.record(started_at=None, provider="groq", model="m", request={}, response=None, reply_text="", duration_ms=0)
        is None
    )
    assert log.entries() == []


def test_purpose_is_unset_outside_the_context() -> None:
    log = LlmTraceLog(max_entries=5)
    with llm_purpose("requirement_extraction"):
        pass
    entry = log.record(
        started_at=None, provider="groq", model="m", request={}, response=None, reply_text="", duration_ms=0
    )
    assert entry is not None and entry.purpose is None

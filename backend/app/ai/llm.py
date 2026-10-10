"""Provider-agnostic LLM interface. `RequirementInterpreter` and
`ExplanationGenerator` call `LlmClient.complete()` without knowing whether
the actual API underneath is Anthropic or Groq - see `app/ai/client.py`
for provider selection (`AI_PROVIDER`).
"""

import time
from collections.abc import Callable
from datetime import datetime
from typing import Any, Protocol

import anthropic
import groq

from app.ai.errors import AiProviderError
from app.ai.trace import trace_log


def _to_provider_error(exc: Exception, connection_error: type[Exception]) -> AiProviderError:
    """Maps an SDK exception to an `AiProviderError`. Anthropic's and
    Groq's SDKs share the same layout (a status-carrying `APIStatusError`
    family plus an `APIConnectionError`), so one mapping serves both.

    Args:
        exc: The SDK exception (`anthropic.APIError` / `groq.APIError`).
        connection_error: That SDK's `APIConnectionError` class (covers
            timeouts too) - the one case with no HTTP status.
    """
    status = getattr(exc, "status_code", None)
    text = str(exc)
    if isinstance(exc, connection_error):
        code = "ai_unreachable"
    elif status in (401, 403):
        code = "ai_invalid_key"
    elif status == 429:
        code = "ai_rate_limited"
    elif status == 404 or (status == 400 and "model" in text.lower()):
        code = "ai_model_unavailable"
    else:
        code = "ai_error"
    return AiProviderError(code, text)


def _traced_create(
    *,
    provider: str,
    request: dict[str, Any],
    create: Callable[..., Any],
    sdk_error: type[Exception],
    connection_error: type[Exception],
    reply_text: Callable[[Any], str],
    usage: Callable[[Any], tuple[int | None, int | None]],
) -> str:
    """Sends `request` through the SDK's `create`, records the whole
    exchange in `app/ai/trace.py`'s `trace_log` (success or failure), and
    returns the reply text. Shared by both adapters so the trace looks the
    same whichever provider is active.

    Args:
        provider: `"groq"` / `"anthropic"`, as shown in the trace.
        request: Keyword arguments for `create` - recorded verbatim.
        create: The SDK's create method.
        sdk_error: That SDK's base `APIError`, mapped via `_to_provider_error`.
        connection_error: That SDK's `APIConnectionError`.
        reply_text: Pulls the reply text out of the SDK response.
        usage: Pulls `(input_tokens, output_tokens)` out of the SDK
            response; `None`s where not reported.

    Raises:
        AiProviderError: The SDK raised `sdk_error`.
    """
    started_at = datetime.now().astimezone()
    started = time.perf_counter()

    def record(**fields: Any) -> None:
        trace_log.record(
            started_at=started_at,
            provider=provider,
            model=str(request.get("model", "")),
            request=request,
            duration_ms=(time.perf_counter() - started) * 1000,
            **fields,
        )

    try:
        response = create(**request)
    except sdk_error as exc:
        error = _to_provider_error(exc, connection_error)
        record(response=getattr(exc, "body", None), reply_text=None, error_code=error.code, error_message=str(error))
        raise error from exc
    except Exception as exc:
        record(response=None, reply_text=None, error_code="exception", error_message=repr(exc))
        raise
    text = reply_text(response)
    input_tokens, output_tokens = usage(response)
    record(response=response, reply_text=text, input_tokens=input_tokens, output_tokens=output_tokens)
    return text


def _usage_tokens(response: Any, input_attr: str, output_attr: str) -> tuple[int | None, int | None]:
    """Reads token counts off `response.usage`, tolerating its absence
    (test fakes, or a provider omitting it).
    """
    usage = getattr(response, "usage", None)
    return getattr(usage, input_attr, None), getattr(usage, output_attr, None)


class LlmClient(Protocol):
    """One system-prompted, single-turn text completion call - the only
    shape `app/ai/requirement_interpreter.py` and
    `app/ai/explanation_generator.py` need from an LLM provider.
    """

    def complete(self, *, system: str, user_content: str, max_tokens: int) -> str:
        """Sends one system+user turn and returns the model's reply text.

        Args:
            system: System prompt.
            user_content: The user-turn content (already fully composed -
                callers build the whole prompt string themselves).
            max_tokens: Upper bound on the reply length.

        Returns:
            The model's text reply, concatenated if the provider returns
            it in multiple parts.

        Raises:
            AiProviderError: The provider rejected or failed the call
                (bad key, rate limit, unknown model, unreachable, ...).
        """
        ...


class AnthropicLlmClient:
    """`LlmClient` backed by the Anthropic Messages API."""

    def __init__(self, client: anthropic.Anthropic, model: str) -> None:
        """Args:
        client: An authenticated Anthropic SDK client.
        model: Model id to pass as `model=` on every call, e.g.
            `CLAUDE_MODEL`.
        """
        self._client = client
        self._model = model

    def complete(self, *, system: str, user_content: str, max_tokens: int) -> str:
        """See `LlmClient.complete`."""
        return _traced_create(
            provider="anthropic",
            request={
                "model": self._model,
                "max_tokens": max_tokens,
                "system": system,
                "messages": [{"role": "user", "content": user_content}],
            },
            create=self._client.messages.create,
            sdk_error=anthropic.APIError,
            connection_error=anthropic.APIConnectionError,
            reply_text=lambda r: "".join(block.text for block in r.content if block.type == "text"),
            usage=lambda r: _usage_tokens(r, "input_tokens", "output_tokens"),
        )


# Groq models that "think" before answering (e.g. `openai/gpt-oss-120b`):
# the thinking tokens are spent from the same completion budget as the
# answer, so a tight `max_tokens` (the explanation call asks for 100) can be
# used up before any answer text - an empty reply. For these models the
# client asks for little thinking, hides it from the reply, and adds
# headroom to the budget. Other models don't take these parameters, so
# they're only sent when the model name matches.
_REASONING_MODEL_PREFIXES = ("openai/gpt-oss",)
_REASONING_HEADROOM_TOKENS = 512


class GroqLlmClient:
    """`LlmClient` backed by Groq's OpenAI-compatible chat completions API."""

    def __init__(self, client: groq.Groq, model: str) -> None:
        """Args:
        client: An authenticated Groq SDK client.
        model: Model id to pass as `model=` on every call, e.g.
            `GROQ_MODEL`.
        """
        self._client = client
        self._model = model

    def complete(self, *, system: str, user_content: str, max_tokens: int) -> str:
        """See `LlmClient.complete`. Groq has no separate `system=`
        parameter (unlike Anthropic) - the system prompt is just the
        first message, with role `"system"`.
        """
        extra: dict = {}
        if self._model.startswith(_REASONING_MODEL_PREFIXES):
            extra = {"reasoning_effort": "low", "include_reasoning": False}
            max_tokens += _REASONING_HEADROOM_TOKENS
        return _traced_create(
            provider="groq",
            request={
                "model": self._model,
                "max_tokens": max_tokens,
                **extra,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user_content},
                ],
            },
            create=self._client.chat.completions.create,
            sdk_error=groq.APIError,
            connection_error=groq.APIConnectionError,
            reply_text=lambda r: r.choices[0].message.content or "",
            usage=lambda r: _usage_tokens(r, "prompt_tokens", "completion_tokens"),
        )

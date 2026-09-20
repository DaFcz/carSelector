"""Provider-agnostic LLM interface. `RequirementInterpreter` and
`ExplanationGenerator` call `LlmClient.complete()` without knowing whether
the actual API underneath is Anthropic or Groq - see `app/ai/client.py`
for provider selection (`AI_PROVIDER`).
"""

from typing import Protocol

import anthropic
import groq

from app.ai.errors import AiProviderError


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
        try:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": user_content}],
            )
        except anthropic.APIError as exc:
            raise _to_provider_error(exc, anthropic.APIConnectionError) from exc
        return "".join(block.text for block in response.content if block.type == "text")


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
        try:
            response = self._client.chat.completions.create(
                model=self._model,
                max_tokens=max_tokens,
                **extra,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user_content},
                ],
            )
        except groq.APIError as exc:
            raise _to_provider_error(exc, groq.APIConnectionError) from exc
        return response.choices[0].message.content or ""

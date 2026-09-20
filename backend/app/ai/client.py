"""Shared LLM client factory. Every AI-provider API call in this codebase
goes through this module - see CLAUDE.md: "Pristup k Claude API pouze pres
/app/ai modul, nikde jinde v kodu." (the same rule now covers Groq too,
the other supported provider - see `AI_PROVIDER`).
"""

from functools import lru_cache

import anthropic
import groq

from app.ai.llm import AnthropicLlmClient, GroqLlmClient, LlmClient
from app.core.config import (
    AI_PROVIDER,
    ANTHROPIC_API_KEY,
    CLAUDE_MODEL,
    GROQ_API_KEY,
    GROQ_MODEL,
)


# API key entered at runtime through the UI (see app/ui/components/
# api_key_dialog.py). Held in process memory only - never written to disk or
# source - and takes priority over the key from the environment/.env, for
# whichever provider `AI_PROVIDER` selects. Lost on restart by design.
_runtime_api_key: str | None = None


class InvalidApiKeyError(ValueError):
    """The entered key has a character that can never be in an API key.

    Attributes:
        position: 1-based position of the first offending character.
        char: That character - safe to show, unlike the key itself.
    """

    def __init__(self, position: int, char: str) -> None:
        super().__init__(f"API key has an invalid character {char!r} at position {position}")
        self.position = position
        self.char = char


def set_runtime_api_key(key: str | None) -> None:
    """Sets (or, with `None`/blank, clears) the runtime API key for the
    provider `AI_PROVIDER` selects, and drops the cached client so the next
    `get_client()` call is built with it.

    Args:
        key: The API key as entered by the user; surrounding whitespace is
            stripped. `None` or blank clears the runtime key, falling back
            to the environment's.

    Raises:
        ValueError: `key` contains non-ASCII characters or inner
            whitespace. No provider's key can (it goes verbatim into an
            HTTP header, where a character like "ě" makes the HTTP layer
            crash before any request is sent), so this is always a typo or
            a paste of something that isn't a key. The previous key is left
            untouched.
    """
    global _runtime_api_key
    cleaned = (key or "").strip() or None
    if cleaned is not None:
        for position, char in enumerate(cleaned, start=1):
            if not (char.isascii() and char.isprintable()) or char == " ":
                raise InvalidApiKeyError(position, char)
    _runtime_api_key = cleaned
    get_client.cache_clear()


def is_configured() -> bool:
    """Whether the selected provider currently has an API key (runtime or
    environment) - i.e. whether `get_client()` would get past the key check.
    """
    return bool(_selected_api_key())


def _selected_api_key() -> str | None:
    """The API key `get_client()` will use: the runtime one if set,
    otherwise the selected provider's environment one."""
    if _runtime_api_key:
        return _runtime_api_key
    return GROQ_API_KEY if AI_PROVIDER == "groq" else ANTHROPIC_API_KEY


@lru_cache(maxsize=1)
def get_client() -> LlmClient:
    """Returns the shared LLM client for whichever provider `AI_PROVIDER`
    selects, creating it on first call.

    A plain cached factory function rather than a class: there's no
    per-instance state or behavior beyond "build once, reuse" - `
    lru_cache(maxsize=1)` already gives that, so a class would only add
    ceremony (see `drivewise-architecture`'s Code style section on when
    a class is/isn't worth it). `RequirementInterpreter` and
    `ExplanationGenerator` each accept a client via dependency injection
    and call this as their default.

    Returns:
        A process-wide singleton `LlmClient` (`AnthropicLlmClient` or
        `GroqLlmClient`, per `AI_PROVIDER`), authenticated with the
        selected provider's API key.

    Raises:
        RuntimeError: `AI_PROVIDER` isn't a recognized value, or the
            selected provider's API key isn't set. Raised here (at first
            use) rather than at import time, so the rest of the app - the
            catalog endpoints in particular - still works without it.
    """
    api_key = _selected_api_key()
    if AI_PROVIDER == "groq":
        if not api_key:
            raise RuntimeError(
                "AI_PROVIDER is 'groq' but GROQ_API_KEY is not set. The AI layer (requirement "
                "extraction, explanations) cannot run without it - set it in the environment or "
                "backend/.env, or switch AI_PROVIDER back to 'anthropic'."
            )
        return GroqLlmClient(groq.Groq(api_key=api_key), GROQ_MODEL)

    if AI_PROVIDER != "anthropic":
        raise RuntimeError(
            f"Unknown AI_PROVIDER {AI_PROVIDER!r} - expected 'anthropic' or 'groq'."
        )
    if not api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not set. The AI layer (requirement "
            "extraction, explanations) cannot run without it - set it in "
            "the environment or backend/.env, or set AI_PROVIDER=groq with a GROQ_API_KEY instead."
        )
    return AnthropicLlmClient(anthropic.Anthropic(api_key=api_key), CLAUDE_MODEL)

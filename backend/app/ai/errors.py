"""Provider-agnostic AI failure type. The `LlmClient` adapters in
`app/ai/llm.py` translate their SDK's exceptions (Anthropic's and Groq's
have the same shape but are different classes) into this, so callers - the
UI and REST layers - can tell "bad key" from "rate limited" without
importing either SDK (see CLAUDE.md: provider access only through `/app/ai`).

Deliberately NOT a `RuntimeError`: that one already means "AI not
configured" (no key at all) across the codebase - see `app/ai/client.py`.
"""


class AiProviderError(Exception):
    """The AI provider rejected or failed a call.

    Attributes:
        code: One of `"ai_invalid_key"` | `"ai_rate_limited"` |
            `"ai_model_unavailable"` | `"ai_unreachable"` | `"ai_error"`.
            Stable, safe to expose to clients and map to user-facing text.
    """

    def __init__(self, code: str, message: str) -> None:
        """Args:
            code: See `code` above.
            message: Developer-facing detail (the SDK's own message).
                Never contains the API key, but is meant for logs, not for
                showing to end users - map `code` to UI text instead.
        """
        super().__init__(message)
        self.code = code

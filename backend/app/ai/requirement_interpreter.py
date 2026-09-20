"""Turns conversation text into StructuredRequirements, or a follow-up
question when the request is underspecified - see the
drivewise-ai-recommendations skill. This module only produces parameters;
it never filters or ranks the catalog itself.

NOTE: written without access to a live API key in this environment, so it
has not been exercised against a real provider. Verify against a real key
before relying on it - in particular, whether the model reliably follows
the JSON-only instruction, whether the defensive fallback below is ever
actually hit in practice, and whether "follow_up_question" actually comes
back in Czech as instructed. This applies independently to each supported
provider (see `AI_PROVIDER`) - a prompt verified against Claude is not
thereby verified against Groq, or vice versa.
"""

import json
import re

from pydantic import BaseModel, ValidationError

from app.ai.client import get_client
from app.ai.llm import LlmClient
from app.schemas.conversation import ChatMessage
from app.schemas.requirement import StructuredRequirements

SYSTEM_PROMPT = """You are the requirement-extraction step of a car-buying assistant.
Read the conversation and the user's latest message, then respond with ONLY a JSON object,
no prose, no markdown code fences, matching this shape:

{
  "requirements": { <StructuredRequirements fields you are confident about, omit the rest> } | null,
  "follow_up_question": "<one focused question>" | null
}

StructuredRequirements fields: body_type (string), min_seats (int), budget_max (object with
amount and currency), fuel_type (string), drivetrain ("fwd" | "rwd" | "awd"),
priorities (list of short strings), notes (string).

Rules:
- Set exactly one of "requirements" or "follow_up_question", never both, never neither.
- Only set "requirements" once there is enough to search: at minimum a body type, a budget, or an
  explicit usage pattern (e.g. "family of 4", "city commuting").
- If the latest message refines a requirement already established earlier in the conversation
  (e.g. "actually make it cheaper"), merge it with what's already known rather than starting over.
- Never invent a value the user didn't state or clearly imply.
- The conversation is in Czech, and the user expects Czech throughout: write "follow_up_question"
  in Czech. JSON keys and the values of body_type/fuel_type/drivetrain stay in English (they're
  internal identifiers, not shown to the user as-is) - only "follow_up_question" is free text a
  person actually reads.
"""


class RequirementExtractionResult(BaseModel):
    requirements: StructuredRequirements | None = None
    follow_up_question: str | None = None


class RequirementInterpreter:
    """Wraps one LLM call that turns free-text conversation into
    `StructuredRequirements`, per `drivewise-ai-recommendations`'s Code
    style section. Stateless beyond the injected client - safe to share a
    single instance across requests (see the module-level `interpreter`
    singleton at the bottom of this file).
    """

    def __init__(self, client: LlmClient | None = None) -> None:
        """Args:
            client: `LlmClient` to use. Defaults to `None`, in which case
                `interpret` lazily resolves the shared client from
                `app.ai.client.get_client()` on first use - so
                constructing a `RequirementInterpreter` never fails just
                because the selected provider's API key isn't set; only
                calling `interpret` does. Pass an explicit client (e.g. a
                test double) to bypass that shared singleton.
        """
        self._client = client

    def _get_client(self) -> LlmClient:
        """Returns the injected client, or lazily resolves the shared
        default on first use so constructing a `RequirementInterpreter`
        never fails just because the selected provider's API key isn't
        set yet (only calling `interpret` does).

        Returns:
            The `LlmClient` this instance uses for API calls.
        """
        # Not cached on `self`: `get_client()` is already a cached singleton,
        # and re-resolving it each time lets a key entered/changed in the UI
        # take effect without a restart.
        return self._client if self._client is not None else get_client()

    @staticmethod
    def _strip_code_fences(text: str) -> str:
        """Removes a leading/trailing ```` ```json ... ``` ```` fence if
        the model added one despite the system prompt's "no markdown code
        fences" instruction.

        Args:
            text: Raw text content from the Claude API response.

        Returns:
            `text` with any surrounding code fence markers and outer
            whitespace stripped; unchanged if there was no fence.
        """
        text = text.strip()
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
        return text.strip()

    def interpret(
        self, history: list[ChatMessage], latest_message: str
    ) -> RequirementExtractionResult:
        """Extracts structured requirements from a conversation turn, or
        produces a follow-up question when there isn't enough to search
        on yet.

        Defensive about the model not following the JSON-only
        instruction: strips stray code fences, validates against
        `RequirementExtractionResult`, and falls back to a generic
        follow-up question on any parse/validation failure rather than
        raising into the request path.

        Args:
            history: Prior turns of the conversation, oldest first. Does
                not include `latest_message`.
            latest_message: The user's newest message, extracted (and
                merged with prior turns) into requirements.

        Returns:
            A `RequirementExtractionResult` with exactly one of
            `requirements` or `follow_up_question` set - never both,
            never neither (enforced by the fallback branch even when the
            model's own output would have violated it).
        """
        client = self._get_client()

        transcript = "\n".join(f"{m.role}: {m.text}" for m in history)
        user_content = f"Conversation so far:\n{transcript}\n\nLatest message:\n{latest_message}"

        raw_text = client.complete(system=SYSTEM_PROMPT, user_content=user_content, max_tokens=1024)

        try:
            payload = json.loads(self._strip_code_fences(raw_text))
            return RequirementExtractionResult.model_validate(payload)
        except (json.JSONDecodeError, ValidationError):
            return RequirementExtractionResult(
                follow_up_question=(
                    "Můžete mi prosím říct trochu více o tom, jak budete auto využívat — kdo s "
                    "vámi pojede, kde nejčastěji jezdíte a jaký je váš přibližný rozpočet?"
                )
            )


# Shared instance for callers that don't need a custom client (e.g. tests
# injecting a fake) - mirrors get_client()'s cached-singleton shape without
# needing its own cache, since construction here does no I/O.
interpreter = RequirementInterpreter()

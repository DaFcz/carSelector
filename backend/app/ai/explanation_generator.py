"""Generates a short, honest per-vehicle explanation once the
recommendation engine has already ranked results - see the
drivewise-ai-recommendations skill. Grounded only in the vehicle's actual
matched attributes; never invents specs.

NOTE: untested against a live API - see requirement_interpreter.py.
"""

from app.ai.client import get_client
from app.ai.llm import LlmClient
from app.schemas.requirement import StructuredRequirements
from app.schemas.vehicle import VehicleSummary

SYSTEM_PROMPT = """You explain a car recommendation in one short sentence (max ~25 words), in Czech
- the user and the rest of the conversation are in Czech (see doc/prompt/CLAUDE.md's language
convention).
Ground the explanation only in the vehicle facts given to you - never invent a feature, spec, or
price the vehicle doesn't have. Plain, factual tone, no marketing language.
"""


class ExplanationGenerator:
    """Wraps one LLM call that turns a ranked vehicle + the requirements
    it matched into a short, fact-grounded sentence, per
    `drivewise-ai-recommendations`'s Code style section. Stateless beyond
    the injected client - safe to share a single instance across requests
    (see the module-level `generator` singleton at the bottom of this
    file).
    """

    def __init__(self, client: LlmClient | None = None) -> None:
        """Args:
            client: `LlmClient` to use. Defaults to `None`, in which case
                `explain` lazily resolves the shared client from
                `app.ai.client.get_client()` on first use - so
                constructing an `ExplanationGenerator` never fails just
                because the selected provider's API key isn't set; only
                calling `explain` does. Pass an explicit client (e.g. a
                test double) to bypass that shared singleton.
        """
        self._client = client

    def _get_client(self) -> LlmClient:
        """Returns the injected client, or lazily resolves the shared
        default on first use.

        Returns:
            The `LlmClient` this instance uses for API calls.
        """
        # Not cached on `self`: `get_client()` is already a cached singleton,
        # and re-resolving it each time lets a key entered/changed in the UI
        # take effect without a restart.
        return self._client if self._client is not None else get_client()

    def explain(self, vehicle: VehicleSummary, requirements: StructuredRequirements) -> str:
        """Generates a one-sentence explanation for why `vehicle` was
        recommended, grounded only in its own listed specs and the
        user's stated priorities.

        Args:
            vehicle: The ranked vehicle to explain. Only `brand`, `model`,
                `trim`, `price`, and `specs` are sent to the model -
                nothing is invented beyond what's already on this object.
            requirements: The structured requirements this vehicle was
                matched against; `priorities` is included as context so
                the explanation can reference what the user said mattered.

        Returns:
            A short (~25 words), factual explanation sentence with
            surrounding whitespace stripped.
        """
        client = self._get_client()
        facts = (
            f"Vehicle: {vehicle.brand} {vehicle.model} {vehicle.trim}\n"
            f"Price: {vehicle.price.amount} {vehicle.price.currency}\n"
            f"Specs: {', '.join(vehicle.specs)}\n"
            f"User priorities: {', '.join(requirements.priorities) or 'none stated'}\n"
        )
        return client.complete(system=SYSTEM_PROMPT, user_content=facts, max_tokens=100).strip()


# Shared instance for callers that don't need a custom client (e.g. tests
# injecting a fake) - mirrors get_client()'s cached-singleton shape without
# needing its own cache, since construction here does no I/O.
generator = ExplanationGenerator()

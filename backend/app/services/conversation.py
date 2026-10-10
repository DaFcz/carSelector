"""Orchestrates one chat turn: AI requirement extraction -> deterministic
recommendation engine -> AI per-vehicle explanations.

Conversation state (message history + accumulated StructuredRequirements)
is held in a process-local in-memory dict, keyed by conversation_id. This
is a deliberate placeholder, not persisted, lost on restart, and won't
work past a single worker process - the DB schema doesn't have
conversation/message tables yet; adding them is a separate design
decision (see doc/api-contract.md "open items").

Because every turn costs paid LLM calls and every conversation costs
memory, both are capped (`app/core/config.py`'s `CHAT_*` settings): message
length, messages per client per hour, conversations started per client per
hour, messages per conversation, and how many conversations are kept (idle
ones expire, the least recently used is dropped when full). A capped call
raises `ConversationLimitError`.
"""

import threading
import time
import uuid
from collections import OrderedDict
from collections.abc import Callable, Collection
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.ai.explanation_generator import ExplanationGenerator
from app.ai.explanation_generator import generator as default_generator
from app.ai.requirement_interpreter import RequirementInterpreter
from app.ai.requirement_interpreter import interpreter as default_interpreter
from app.core import config
from app.schemas.conversation import ChatMessage, MessageResponse
from app.schemas.requirement import StructuredRequirements, UserRequirement
from app.services.rate_limit import SlidingWindowLimiter
from app.services.recommendation_engine import RecommendationEngine
from app.services.recommendation_engine import engine as default_engine

DEFAULT_LANGUAGE = "cs"

# The assistant's fixed (non-AI) chat copy, per conversation language
# ("cs" | "en" - see `ConversationOrchestrator.start_conversation`). Lives
# here rather than in `app/ui/i18n.py` because the REST API
# (`app/api/conversations.py`) returns it too, not just the UI.
_MESSAGES = {
    "cs": {
        "intro": (
            "Ahoj! Řekněte mi, jak budete své nové auto využívat — kde jezdíte, kdo s vámi jezdí, "
            "co je pro vás nejdůležitější — a já to přetavím do konkrétních parametrů a vyberu vám "
            "reálné vozy k porovnání."
        ),
        "follow_up": "Můžete mi prosím říct trochu více o tom, co potřebujete?",
        "updated": ("Na základě toho, co jste mi řekli, jsem aktualizoval váš výběr — aktuálně vyhovuje {count} vozů."),
        "no_match": "Aktualizoval jsem vaše požadavky, ale v katalogu zatím nic nevyhovuje — chcete něco uvolnit?",
    },
    "en": {
        "intro": (
            "Hi! Tell me how you'll use your new car — where you drive, who rides with you, "
            "what matters most to you — and I'll turn that into concrete parameters and pick "
            "real cars for you to compare."
        ),
        "follow_up": "Could you tell me a bit more about what you need?",
        "updated": "Based on what you've told me, I've updated your selection — {count} cars currently match.",
        "no_match": "I've updated your requirements, but nothing in the catalog matches yet — want to relax something?",
    },
}

# Requirement-card labels, in display order.
_FIELD_LABELS = {
    "cs": {
        "body_type": "Karoserie",
        "min_seats": "Počet míst",
        "budget_max": "Rozpočet",
        "fuel_type": "Palivo",
        "drivetrain": "Pohon",
        "priorities": "Priority",
        "notes": "Poznámky",
    },
    "en": {
        "body_type": "Body type",
        "min_seats": "Seats",
        "budget_max": "Budget",
        "fuel_type": "Fuel",
        "drivetrain": "Drive",
        "priorities": "Priorities",
        "notes": "Notes",
    },
}


@dataclass
class _ConversationState:
    history: list[ChatMessage] = field(default_factory=list)
    requirements: StructuredRequirements = field(default_factory=StructuredRequirements)
    language: str = DEFAULT_LANGUAGE
    # The starting client's key (IP), used for per-client limits when a
    # later call doesn't name one; `None` if unknown.
    client_key: str | None = None
    # Monotonic time of the last start/turn - see `_evict`.
    last_active: float = 0.0
    # Turns taken so far (chat messages and wizard submissions).
    turns: int = 0


class UnknownConversationError(KeyError):
    pass


class ConversationLimitError(Exception):
    """A call was refused by one of the chat abuse limits (see the module
    docstring).

    Attributes:
        code: `"message_too_long"` | `"rate_limited"` |
            `"conversation_too_long"` - stable, safe to show to users.
    """

    def __init__(self, code: str) -> None:
        """Args:
        code: See `code` above.
        """
        super().__init__(code)
        self.code = code


class ConversationOrchestrator:
    """Owns in-memory conversation state and drives one chat turn through
    the AI layer and recommendation engine, per
    `drivewise-ai-recommendations`'s Code style section. The
    `_conversations` dict is real per-instance state (not just an
    injected dependency), which is exactly the case for a class per
    `drivewise-architecture`'s Code style section - previously a bare
    module-level global, now encapsulated here instead.
    """

    # Bounds how many of `recommend()`'s (now-unlimited, see that method's
    # own docstring) results get an AI-generated explanation - a genuine
    # per-result cap, unlike RecommendationEngine's old limit=10, which
    # used to hide real matches from the user entirely. This one only
    # trims a Claude API call each result would otherwise cost (a wizard
    # answer matching hundreds of vehicles would otherwise fire hundreds
    # of explanation calls in one turn) - every vehicle past this point
    # still reaches `vehicles`/the UI, just without its own explanation
    # sentence (`VehicleSummary.explanation` is already optional, and
    # `results_grid.py`'s card only renders the line when it's set).
    EXPLANATION_LIMIT = 10

    def __init__(
        self,
        requirement_interpreter: RequirementInterpreter | None = None,
        recommendation_engine: RecommendationEngine | None = None,
        explanation_generator: ExplanationGenerator | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        """Args:
        requirement_interpreter: Turns conversation text into
            structured requirements. Defaults to the shared
            `app.ai.requirement_interpreter.interpreter` singleton.
        recommendation_engine: Filters and ranks the catalog. Defaults
            to the shared
            `app.services.recommendation_engine.engine` singleton.
        explanation_generator: Generates per-vehicle explanations.
            Defaults to the shared
            `app.ai.explanation_generator.generator` singleton.
        clock: Monotonic time source for expiry and rate limits (a
            parameter so tests control it).
        """
        self._requirement_interpreter = requirement_interpreter or default_interpreter
        self._recommendation_engine = recommendation_engine or default_engine
        self._explanation_generator = explanation_generator or default_generator
        self._clock = clock
        # Least recently used first (see `_begin_turn`), which is what
        # `_evict` relies on.
        self._conversations: OrderedDict[str, _ConversationState] = OrderedDict()
        self._lock = threading.Lock()
        self._message_limiter = SlidingWindowLimiter(config.CHAT_MAX_MESSAGES_PER_CLIENT_HOUR, 3600, clock)
        self._start_limiter = SlidingWindowLimiter(config.CHAT_MAX_CONVERSATIONS_PER_CLIENT_HOUR, 3600, clock)

    def start_conversation(self, language: str = DEFAULT_LANGUAGE, client_key: str | None = None) -> tuple[str, str]:
        """Creates a new, empty conversation.

        Args:
            language: `"cs"` or `"en"` - the language of every assistant
                reply in this conversation, AI-generated text included.
                Anything else falls back to `DEFAULT_LANGUAGE`.
            client_key: Who is starting it (the client's IP), for the
                per-client limits; `None` if unknown.

        Returns:
            A `(conversation_id, intro_message)` pair - `conversation_id`
            identifies this conversation for subsequent `handle_message`
            calls, `intro_message` is the assistant's opening line to
            show the user immediately.

        Raises:
            ConversationLimitError: `"rate_limited"` - this client started
                too many conversations in the last hour.
        """
        if client_key is not None and not self._start_limiter.hit(client_key):
            raise ConversationLimitError("rate_limited")
        conversation_id = str(uuid.uuid4())
        if language not in _MESSAGES:
            language = DEFAULT_LANGUAGE
        now = self._clock()
        with self._lock:
            self._evict(now)
            self._conversations[conversation_id] = _ConversationState(
                language=language, client_key=client_key, last_active=now
            )
        return conversation_id, _MESSAGES[language]["intro"]

    def _evict(self, now: float) -> None:
        """Drops idle conversations, then the least recently used ones
        until there is room for one more. Caller holds `_lock`.

        Args:
            now: Current monotonic time.
        """
        idle_cutoff = now - config.CHAT_CONVERSATION_IDLE_MINUTES * 60
        while self._conversations and next(iter(self._conversations.values())).last_active <= idle_cutoff:
            self._conversations.popitem(last=False)
        if config.CHAT_MAX_CONVERSATIONS > 0:
            while len(self._conversations) >= config.CHAT_MAX_CONVERSATIONS:
                self._conversations.popitem(last=False)

    def _begin_turn(self, conversation_id: str, client_key: str | None, text: str | None) -> _ConversationState:
        """Looks up the conversation and checks every per-turn limit -
        length and conversation size first, so a refused call doesn't use
        up the client's hourly budget.

        Args:
            conversation_id: The conversation to take a turn in.
            client_key: The caller (client IP), if known; otherwise the
                key the conversation was started with is used, and failing
                that the conversation itself.
            text: The user's free text to length-check, or `None` when the
                turn carries none (wizard answers are built server-side).

        Returns:
            The conversation's state, marked as just used.

        Raises:
            UnknownConversationError: No such conversation, or it expired.
            ConversationLimitError: See `ConversationLimitError.code`.
        """
        now = self._clock()
        with self._lock:
            state = self._conversations.get(conversation_id)
            if state is None or state.last_active <= now - config.CHAT_CONVERSATION_IDLE_MINUTES * 60:
                self._conversations.pop(conversation_id, None)
                raise UnknownConversationError(conversation_id)
            if text is not None and 0 < config.CHAT_MAX_MESSAGE_LENGTH < len(text):
                raise ConversationLimitError("message_too_long")
            if 0 < config.CHAT_MAX_MESSAGES_PER_CONVERSATION <= state.turns:
                raise ConversationLimitError("conversation_too_long")
            if not self._message_limiter.hit(client_key or state.client_key or f"conversation:{conversation_id}"):
                raise ConversationLimitError("rate_limited")
            state.turns += 1
            state.last_active = now
            self._conversations.move_to_end(conversation_id)
            return state

    @staticmethod
    def _merge_requirements(
        existing: StructuredRequirements, update: StructuredRequirements
    ) -> tuple[StructuredRequirements, set[str]]:
        """Merges only the fields the AI actually populated this turn and
        reports which fields changed, so the UI can flash updated cards.

        Args:
            existing: Requirements accumulated so far this conversation.
            update: Newly extracted requirements from this turn - fields
                the model left unset are `None`/empty and ignored.

        Returns:
            A `(merged, changed)` pair: `merged` is `existing` with every
            non-empty field from `update` applied; `changed` is the set
            of field names whose value was actually different from
            `existing` (used to flag which requirement cards changed).
        """
        changed: set[str] = set()
        merged_data = existing.model_dump()
        for field_name, value in update.model_dump().items():
            if value in (None, [], ""):
                continue
            if merged_data.get(field_name) != value:
                changed.add(field_name)
            merged_data[field_name] = value
        return StructuredRequirements.model_validate(merged_data), changed

    @staticmethod
    def _to_user_requirements(
        requirements: StructuredRequirements,
        changed: set[str],
        source_message: str,
        language: str = DEFAULT_LANGUAGE,
    ) -> list[UserRequirement]:
        """Builds the human-readable "requirements drawer" cards for one
        turn's requirements snapshot.

        Args:
            requirements: The (possibly just-merged) requirements to
                render as cards - one card per populated field.
            changed: Field names to mark `changed=True` on their card
                (drives the UI's flash-on-update animation).
            source_message: The user message these requirements were
                extracted from, shown as the card's quoted source.
            language: Language of the card labels.

        Returns:
            One `UserRequirement` card per populated field of
            `requirements`, in `_FIELD_LABELS`'s display order.
        """
        cards = []
        for field_name, label in _FIELD_LABELS[language].items():
            value = getattr(requirements, field_name)
            if value in (None, [], ""):
                continue
            if field_name == "budget_max":
                display_value = f"{value.amount:,.0f} {value.currency}"
            elif field_name == "priorities":
                display_value = ", ".join(value)
            elif hasattr(value, "value"):
                display_value = str(value.value)
            else:
                display_value = str(value)
            cards.append(
                UserRequirement(
                    label=label,
                    value=display_value,
                    source=f'"{source_message}"',
                    changed=field_name in changed,
                )
            )
        return cards

    def handle_message(
        self,
        db: Session,
        conversation_id: str,
        text: str,
        *,
        liked_model_ids: Collection[int] = (),
        client_key: str | None = None,
    ) -> MessageResponse:
        """Processes one user message: extracts/merges requirements, then
        (once there's enough to search on) filters, ranks, and explains
        matching vehicles.

        Args:
            db: Database session to query the catalog through.
            conversation_id: Id returned by an earlier `start_conversation`
                call.
            text: The user's new message.
            liked_model_ids: The user's liked models - a ranking boost,
                see `RecommendationEngine.recommend`.
            client_key: The caller (client IP) for the per-client limit,
                if known - see `_begin_turn`.

        Returns:
            The assistant's reply for this turn: either a follow-up
            question (if requirements are still underspecified, in which
            case `vehicles` is empty and `searched` is `False`) or an
            updated shortlist (`searched=True`, though `vehicles` can
            still legitimately be empty - nothing matched) with
            explanations where the AI layer is configured.

        Raises:
            UnknownConversationError: `conversation_id` doesn't match any
                conversation started via `start_conversation` (e.g. it
                expired, or the process restarted - state isn't
                persisted, see the module docstring).
            ConversationLimitError: A chat abuse limit refused the turn -
                see the module docstring.
        """
        state = self._begin_turn(conversation_id, client_key, text)

        extraction = self._requirement_interpreter.interpret(state.history, text, language=state.language)

        if extraction.requirements is None:
            state.history.append(ChatMessage(role="user", text=text))
            assistant_text = extraction.follow_up_question or _MESSAGES[state.language]["follow_up"]
            state.history.append(ChatMessage(role="assistant", text=assistant_text))
            return MessageResponse(
                assistant_text=assistant_text,
                requirements=self._to_user_requirements(state.requirements, set(), text, state.language),
                structured_requirements=state.requirements,
                vehicles=[],
                searched=False,
            )

        return self._apply_requirements(db, state, extraction.requirements, text, liked_model_ids)

    def handle_wizard_answers(
        self,
        db: Session,
        conversation_id: str,
        requirements: StructuredRequirements,
        summary_message: str,
        *,
        liked_model_ids: Collection[int] = (),
        client_key: str | None = None,
    ) -> MessageResponse:
        """Applies requirements captured directly by the step-by-step
        wizard (see `app/ui/components/wizard.py`), skipping the AI
        requirement-extraction step entirely since the input is already
        structured - there is nothing for the AI to misinterpret. Runs
        the same deterministic recommend-then-explain pipeline as
        `handle_message`'s narrowed-search branch, so wizard-driven and
        chat-driven turns end up in one shared conversation/requirements
        state.

        Args:
            db: Database session to query the catalog through.
            conversation_id: Id returned by an earlier `start_conversation`
                call.
            requirements: Requirements built from the wizard's answers
                (see `WizardState.to_structured_requirements`).
            summary_message: Human-readable recap of the wizard's answers,
                recorded as this turn's "user" transcript entry (there is
                no free-text message to store instead).
            liked_model_ids: The user's liked models - a ranking boost,
                see `RecommendationEngine.recommend`.
            client_key: The caller (client IP) for the per-client limit,
                if known - see `_begin_turn`.

        Returns:
            Same shape as `handle_message`'s narrowed-search branch:
            `searched=True`, `vehicles` possibly empty if nothing matches.

        Raises:
            UnknownConversationError: `conversation_id` doesn't match any
                conversation started via `start_conversation`, or it
                expired.
            ConversationLimitError: `"rate_limited"` or
                `"conversation_too_long"` - see the module docstring.
        """
        state = self._begin_turn(conversation_id, client_key, None)

        return self._apply_requirements(db, state, requirements, summary_message, liked_model_ids)

    def _apply_requirements(
        self,
        db: Session,
        state: "_ConversationState",
        update: StructuredRequirements,
        source_message: str,
        liked_model_ids: Collection[int] = (),
    ) -> MessageResponse:
        """Shared tail of `handle_message` and `handle_wizard_answers`:
        merges newly-known requirements into `state`, then filters,
        ranks, and explains matching vehicles.

        Args:
            db: Database session to query the catalog through.
            state: The conversation's accumulated state - mutated in
                place (`state.requirements`) and appended to
                (`state.history`).
            update: Newly-known requirements to merge in, from either the
                AI extraction step or the wizard.
            source_message: Recorded as this turn's "user" transcript
                entry and shown as the source quote on changed
                requirement cards.
            liked_model_ids: The user's liked models, passed through to
                the recommendation engine's ranking.

        Returns:
            The assistant's reply for this turn - `searched=True`, though
            `vehicles` can still legitimately be empty.
        """
        merged, changed = self._merge_requirements(state.requirements, update)
        state.requirements = merged
        state.history.append(ChatMessage(role="user", text=source_message))

        vehicles = self._recommendation_engine.recommend(db, merged, liked_model_ids=liked_model_ids)

        explained = []
        for index, vehicle in enumerate(vehicles):
            if index >= self.EXPLANATION_LIMIT:
                explained.append(vehicle)
                continue
            try:
                explanation = self._explanation_generator.explain(vehicle, merged, language=state.language)
            except RuntimeError:
                # AI layer not configured (no ANTHROPIC_API_KEY) - degrade to
                # an unexplained result rather than failing the whole request.
                explanation = None
            explained.append(vehicle.model_copy(update={"explanation": explanation}) if explanation else vehicle)

        messages = _MESSAGES[state.language]
        assistant_text = messages["updated"].format(count=len(explained)) if explained else messages["no_match"]
        state.history.append(ChatMessage(role="assistant", text=assistant_text))

        return MessageResponse(
            assistant_text=assistant_text,
            requirements=self._to_user_requirements(merged, changed, source_message, state.language),
            structured_requirements=merged,
            vehicles=explained,
            searched=True,
        )


# Shared instance the API layer uses (app/api/conversations.py) - holds
# the actual conversation state, so unlike the AI-layer/engine singletons
# it isn't just a construction-is-cheap convenience; this one *must* be
# shared across requests within a process for conversations to work at
# all (see the module docstring on why that's a known limitation).
orchestrator = ConversationOrchestrator()

"""Per-connection UI state, replacing the former frontend's two Zustand
stores (`conversationStore`, `catalogStore`) plus the side-effect logic
that lived in `hooks/useConversation.ts` / `hooks/useCatalog.ts` /
`hooks/useVehicleDetail.ts`. A `@ui.page` function's local variables are
already private to one browser connection (NiceGUI's per-client-closure
model - see `app/ui/pages.py`), so these are plain dataclasses instantiated
once per page load, not global state - the direct analogue of a Zustand
store scoped to a single mounted React tree instead of the whole app.

Every service-layer call here goes through `nicegui.run.io_bound` so the
synchronous SQLAlchemy/orchestrator calls never block the event loop other
connections share - see `app/ui/db.py`.
"""

import logging
from collections.abc import MutableMapping
from dataclasses import dataclass, field

from nicegui import run

from app.ai.errors import AiProviderError
from app.models.enums import Drivetrain, FuelType
from app.schemas.catalog import BrandRead, TrimChoice
from app.schemas.common import Money
from app.schemas.requirement import StructuredRequirements, UserRequirement
from app.schemas.sharing import SharedSnapshot
from app.schemas.vehicle import VehicleDetail, VehicleSummary
from app.services import catalog, liked_models, saved_requirements, sharing
from app.services.conversation import orchestrator
from app.ui import db as ui_db
from app.ui.compare import MAX_COMPARE
from app.ui.i18n import DEFAULT_LANGUAGE, t

# Mirrors frontend/src/types/conversation.ts's ChatMessage.
ChatMessage = tuple[str, str]  # (role, text) - role is "user" | "assistant"

logger = logging.getLogger(__name__)

PAGE_SIZE = 20


@dataclass
class LikedModelsState:
    """Which car models this session has liked (the heart on a results
    card). Anonymous likes live only here, for this page load; a logged-in
    user's are also persisted to their account (see
    `app/services/liked_models.py`), and a mid-session login merges the
    anonymous ones in (`on_login`).

    Read by `ConversationState`/`CatalogState` through `ids` to boost
    liked models in the next search - an already-rendered result list is
    not reordered under the user's finger when they like a card.
    """

    model_ids: set[int] = field(default_factory=set)
    # Same contract as `ConversationState.user_id` - set by
    # `app/ui/pages.py` from `AuthState`, `None` while logged out.
    user_id: int | None = None

    @property
    def ids(self) -> frozenset[int]:
        """An immutable snapshot of `model_ids`, safe to hand to a
        background thread (`run.io_bound`) while the UI keeps mutating
        the live set."""
        return frozenset(self.model_ids)

    def is_liked(self, model_id: int) -> bool:
        """Args:
            model_id: The `models` row to check.

        Returns:
            Whether this session has that model liked.
        """
        return model_id in self.model_ids

    async def load(self) -> None:
        """Replaces the session's likes with `user_id`'s saved ones - on
        page load for an already-logged-in user. No-op while logged out.
        A failure is logged and leaves the likes as they were, same
        swallow-and-log handling as `ConversationState`'s saved
        requirements."""
        if self.user_id is None:
            return
        user_id = self.user_id

        def _load() -> set[int]:
            with ui_db.get_session() as db:
                return liked_models.list_ids(db, user_id)

        try:
            self.model_ids = await run.io_bound(_load)
        except Exception:
            logger.exception("Loading liked models for user %s failed", user_id)

    async def toggle(self, model_id: int) -> bool:
        """Likes `model_id` if it isn't liked yet, unlikes it otherwise -
        in this session right away, and in the account too if logged in.

        Args:
            model_id: The `models` row whose heart was clicked.

        Returns:
            Whether the model is liked after the toggle.
        """
        now_liked = model_id not in self.model_ids
        if now_liked:
            self.model_ids.add(model_id)
        else:
            self.model_ids.discard(model_id)

        if self.user_id is not None:
            user_id = self.user_id

            def _save() -> None:
                with ui_db.get_session() as db:
                    if now_liked:
                        liked_models.like(db, user_id, model_id)
                    else:
                        liked_models.unlike(db, user_id, model_id)

            try:
                await run.io_bound(_save)
            except Exception:
                logger.exception("Saving a like for user %s failed", user_id)
        return now_liked

    async def on_login(self) -> None:
        """Called right after `user_id` is set mid-session: saves the
        likes gathered anonymously under the account, then loads the
        account's full set (the union of both)."""
        if self.user_id is None:
            return
        user_id = self.user_id
        anonymous = self.ids

        def _merge() -> set[int]:
            with ui_db.get_session() as db:
                liked_models.like_many(db, user_id, anonymous)
                return liked_models.list_ids(db, user_id)

        try:
            self.model_ids = await run.io_bound(_merge)
        except Exception:
            logger.exception("Merging liked models for user %s failed", user_id)

    def on_logout(self) -> None:
        """Forgets the likes - they belong to the account that just
        logged out, not to the anonymous session that remains."""
        self.user_id = None
        self.model_ids = set()


def _liked_ids(liked: LikedModelsState | None) -> frozenset[int]:
    return liked.ids if liked is not None else frozenset()


@dataclass
class ConversationState:
    """The chat/narrowing side of the page - AI-driven conversation state.

    Mirrors `conversationStore` + `useConversation`'s combined state and
    behavior. `error` is one of `"ai_not_configured"` |
    an `AiProviderError.code` (`"ai_invalid_key"`, `"ai_rate_limited"`, ...)
    | `"unknown_error"` | `None` - there's no `"network_error"` case here (unlike the old
    frontend's `ApiError`), since calling the orchestrator in-process has
    no network hop to fail.
    """

    conversation_id: str | None = None
    messages: list[ChatMessage] = field(default_factory=list)
    requirements: list[UserRequirement] = field(default_factory=list)
    # The same requirements as `requirements` above, but the raw schema
    # rather than its display cards - `UserRequirement` only carries a
    # formatted string per populated field, which isn't reliably
    # reconstructible back into a `StructuredRequirements` (e.g. an enum's
    # `.value`, or several notes concatenated into one string). Kept
    # alongside it purely so a logged-in user's requirements can be
    # persisted (see `_persist_saved_requirements`) without that lossy
    # round-trip.
    structured_requirements: StructuredRequirements = field(default_factory=StructuredRequirements)
    cars: list[VehicleSummary] = field(default_factory=list)
    # True once the recommendation engine has actually run at least once
    # (a turn's `searched=True`). Distinguishes "AI hasn't narrowed
    # anything yet" (show the full catalog) from "AI searched and found
    # nothing" (both leave `cars` empty) - only `restart()` clears it.
    has_narrowed: bool = False
    drawer_open: bool = False
    is_loading: bool = False
    is_sending: bool = False
    error: str | None = None
    # Whose account to persist requirements under - `None` while
    # logged out. Set by `app/ui/pages.py` from `AuthState`, both at page
    # load and on a mid-session login/logout; `ConversationState` itself
    # never reads `AuthState` to stay decoupled from the auth layer.
    user_id: int | None = None
    # The page's likes, passed to every search as a ranking boost - see
    # `LikedModelsState`. `None` means "no likes" (e.g. in tests).
    liked: LikedModelsState | None = None
    # Language of the assistant's replies and AI-generated text ("cs" |
    # "en") - set by `app/ui/pages.py` from the browser's choice (see
    # `app/ui/i18n.py`'s `current_language`). Fixed for one conversation:
    # switching language reloads the page, which starts a new one.
    language: str = DEFAULT_LANGUAGE

    async def begin(self) -> None:
        """Starts a new conversation and seeds the transcript with its
        opening message, then - if `user_id` is set - restores that
        user's saved requirements (see `_restore_saved_requirements`) so
        a logged-in user doesn't start from a blank slate on every reload.
        `start_conversation` is pure in-memory (uuid + dict), so that part
        is called directly rather than through `run.io_bound`.
        """
        self.is_loading = True
        self.error = None
        try:
            conversation_id, intro_message = orchestrator.start_conversation(self.language)
            self.conversation_id = conversation_id
            self.messages = [("assistant", intro_message)]
            if self.user_id is not None:
                await self._restore_saved_requirements()
        except Exception:
            self.error = "unknown_error"
        finally:
            self.is_loading = False

    async def _restore_saved_requirements(self) -> None:
        """Loads `self.user_id`'s saved requirements, if any, and applies
        them to this freshly-started conversation - same effect as the
        user re-submitting the wizard with those answers, so the results
        grid ends up matching what the drawer shows. A failure here is
        logged and otherwise swallowed: it would be worse to fail the
        whole page load over a saved-requirements hiccup than to just
        start from a blank conversation, same reasoning as
        `CatalogState.load_brands`'s empty-on-failure fallback.
        """
        user_id = self.user_id

        def _load() -> StructuredRequirements | None:
            with ui_db.get_session() as db:
                return saved_requirements.load(db, user_id)

        try:
            saved = await run.io_bound(_load)
            if saved is None:
                return
            conversation_id = self.conversation_id
            liked_ids = _liked_ids(self.liked)
            # Stands in for a real chat message - shown as the "user" bubble
            # right before the assistant's reply, the same way a wizard-answer
            # summary does, since `orchestrator.handle_wizard_answers` needs
            # *some* source_message to attribute the turn to.
            summary_message = t("chat.restoreSummary", lang=self.language)

            def _restore() -> object:
                with ui_db.get_session() as db:
                    return orchestrator.handle_wizard_answers(
                        db, conversation_id, saved, summary_message, liked_model_ids=liked_ids
                    )

            self.messages.append(("user", summary_message))
            result = await run.io_bound(_restore)
            self.messages.append(("assistant", result.assistant_text))
            self.requirements = result.requirements
            self.structured_requirements = result.structured_requirements
            self.cars = result.vehicles
            self.has_narrowed = True
        except Exception:
            logger.exception("Restoring saved requirements for user %s failed", user_id)

    async def _persist_saved_requirements(self) -> None:
        """Saves `self.structured_requirements` under `self.user_id`, if
        logged in and there's actually something populated to save yet
        (skips the early turns of a conversation, where every field is
        still unset). Called after every turn that could have changed
        the requirements (`send`, `send_wizard_answers`) and once
        immediately after a mid-session login (see
        `app/ui/pages.py`'s `on_logged_in`) so answers already given
        anonymously this session start being remembered right away
        rather than only from the next turn onward. A failure here is
        logged and swallowed - losing the save shouldn't surface as a
        chat error, since the turn itself already succeeded.
        """
        if self.user_id is None or self.structured_requirements == StructuredRequirements():
            return
        user_id = self.user_id
        requirements = self.structured_requirements

        def _save() -> None:
            with ui_db.get_session() as db:
                saved_requirements.save(db, user_id, requirements)

        try:
            await run.io_bound(_save)
        except Exception:
            logger.exception("Saving requirements for user %s failed", user_id)

    async def on_login(self) -> None:
        """Public entry point for `app/ui/pages.py`'s `on_logged_in`,
        called right after `self.user_id` is set to the account that just
        logged in mid-session (not the initial-page-load case - that one
        goes through `begin()` instead, since a fresh conversation only
        exists there):

        - If this session already has requirements gathered anonymously
          (`self.structured_requirements` is non-empty), saves them under
          the new account right away rather than waiting for the next
          chat/wizard turn - see `_persist_saved_requirements`.
        - Otherwise (nothing gathered yet this session - e.g. the page
          was reloaded while logged out, landing on a blank conversation,
          before logging back in), restores that account's previously
          saved requirements instead, same as `begin()` does for an
          already-logged-in page load - see
          `_restore_saved_requirements`. Without this branch, logging
          back in on a fresh conversation looked like the save had
          silently failed: nothing to persist (already empty) and
          nothing ever loaded it back either.
        """
        if self.structured_requirements != StructuredRequirements():
            await self._persist_saved_requirements()
        else:
            await self._restore_saved_requirements()

    async def _clear_saved_requirements(self) -> None:
        """Deletes `self.user_id`'s saved requirements, if logged in -
        called by `restart()` so starting over also forgets the old
        requirements server-side. Same swallow-and-log failure handling
        as `_persist_saved_requirements`.
        """
        if self.user_id is None:
            return
        user_id = self.user_id

        def _clear() -> None:
            with ui_db.get_session() as db:
                saved_requirements.clear(db, user_id)

        try:
            await run.io_bound(_clear)
        except Exception:
            logger.exception("Clearing saved requirements for user %s failed", user_id)

    async def send(self, text: str) -> None:
        """Sends `text` as the user's next message and applies the
        result. No-ops if already sending, the message is blank, or the
        conversation hasn't started yet.

        Args:
            text: The user's message.
        """
        trimmed = text.strip()
        if not trimmed or self.is_sending or self.conversation_id is None:
            return

        self.messages.append(("user", trimmed))
        self.is_sending = True
        self.error = None
        conversation_id = self.conversation_id
        liked_ids = _liked_ids(self.liked)

        def _send() -> object:
            with ui_db.get_session() as db:
                return orchestrator.handle_message(db, conversation_id, trimmed, liked_model_ids=liked_ids)

        try:
            result = await run.io_bound(_send)
            self.messages.append(("assistant", result.assistant_text))
            self.requirements = result.requirements
            self.structured_requirements = result.structured_requirements
            self.cars = result.vehicles
            self.has_narrowed = self.has_narrowed or result.searched
            await self._persist_saved_requirements()
        except RuntimeError:
            # AI layer not configured (missing ANTHROPIC_API_KEY) - see
            # app/ai/client.py.
            self.error = "ai_not_configured"
        except AiProviderError as exc:
            logger.warning("AI provider call failed (%s): %s", exc.code, exc)
            self.error = exc.code
        except Exception:
            logger.exception("Sending a chat message failed")
            self.error = "unknown_error"
        finally:
            self.is_sending = False

    async def send_wizard_answers(self, requirements: StructuredRequirements, summary_message: str) -> None:
        """Applies requirements collected by the guided wizard (see
        `WizardState`) - the wizard's counterpart to `send`. Skips
        straight to the recommend/explain step since the answers are
        already structured; there is no free text for the AI to
        interpret, so (unlike `send`) this never sets
        `error = "ai_not_configured"`. No-ops if already sending or the
        conversation hasn't started yet.

        Args:
            requirements: Structured requirements built from the
                wizard's answers (see `WizardState.to_structured_requirements`).
            summary_message: Human-readable recap of the answers, shown
                as this turn's "user" chat bubble.
        """
        if self.is_sending or self.conversation_id is None:
            return

        self.messages.append(("user", summary_message))
        self.is_sending = True
        self.error = None
        conversation_id = self.conversation_id
        liked_ids = _liked_ids(self.liked)

        def _send() -> object:
            with ui_db.get_session() as db:
                return orchestrator.handle_wizard_answers(
                    db, conversation_id, requirements, summary_message, liked_model_ids=liked_ids
                )

        try:
            result = await run.io_bound(_send)
            self.messages.append(("assistant", result.assistant_text))
            self.requirements = result.requirements
            self.structured_requirements = result.structured_requirements
            self.cars = result.vehicles
            self.has_narrowed = True
            await self._persist_saved_requirements()
        except AiProviderError as exc:
            # Only the explanation step calls the AI here (no free text to
            # interpret), but it can still be rejected - e.g. a bad key.
            logger.warning("AI provider call failed (%s): %s", exc.code, exc)
            self.error = exc.code
        except Exception:
            logger.exception("Applying the wizard's answers failed")
            self.error = "unknown_error"
        finally:
            self.is_sending = False

    async def restart(self) -> None:
        """Abandons the current conversation and starts a fresh one - for
        a logged-in user, also forgets their saved requirements
        server-side (`_clear_saved_requirements`), so "starting over"
        doesn't just get silently undone by `begin()` restoring the old
        ones again on the very next reload.
        """
        await self._clear_saved_requirements()
        self.conversation_id = None
        self.messages = []
        self.requirements = []
        self.structured_requirements = StructuredRequirements()
        self.cars = []
        self.has_narrowed = False
        self.drawer_open = False
        self.error = None
        await self.begin()

    def toggle_drawer(self) -> None:
        """Opens the requirements drawer if closed, closes it if open."""
        self.drawer_open = not self.drawer_open

    def close_drawer(self) -> None:
        """Closes the requirements drawer."""
        self.drawer_open = False


@dataclass
class WizardState:
    """Guided step-by-step alternative to the free-text chat for building
    `StructuredRequirements`, aimed at non-technical users - see
    `doc/ai/wizard-questions.md`. Deterministic: answers map straight
    onto `StructuredRequirements` in `to_structured_requirements` below,
    so (unlike the chat's `RequirementInterpreter`) it needs no AI call
    and works even without `ANTHROPIC_API_KEY` configured - only the
    per-vehicle explanation step, shared with the chat path via
    `ConversationOrchestrator._apply_requirements`, degrades in that case.

    All display text (question wording, option labels) lives in
    `app/ui/components/wizard.py` via `t()` - this class holds identifiers
    only (e.g. `"awd"`, `"cargo"`), never Czech copy, the same split
    `CatalogState`'s enum-valued filters keep.
    """

    STEP_COUNT = 10

    is_open: bool = False
    step: int = 0
    budget: float | None = None
    usage: str | None = None
    seats: int | None = None
    body_type: str | None = None
    needs_awd: bool | None = None
    fuel_pattern: str | None = None
    annual_km: int | None = None
    cargo_need: str | None = None
    brand_pref: str = ""
    priority: str | None = None

    def open_wizard(self) -> None:
        """Clears any previous answers and opens the wizard at its first step."""
        self.is_open = True
        self.step = 0
        self.budget = None
        self.usage = None
        self.seats = None
        self.body_type = None
        self.needs_awd = None
        self.fuel_pattern = None
        self.annual_km = None
        self.cargo_need = None
        self.brand_pref = ""
        self.priority = None

    def close(self) -> None:
        """Closes the wizard without applying its (partial) answers."""
        self.is_open = False

    def go_next(self) -> None:
        """Advances to the next step, capped at the last one."""
        self.step = min(self.step + 1, self.STEP_COUNT - 1)

    def go_back(self) -> None:
        """Returns to the previous step, capped at the first one."""
        self.step = max(self.step - 1, 0)

    @property
    def is_last_step(self) -> bool:
        """True on the wizard's final step (its "Finish" step)."""
        return self.step == self.STEP_COUNT - 1

    def to_structured_requirements(self) -> StructuredRequirements:
        """Maps the collected answers onto the same `StructuredRequirements`
        shape the AI requirement interpreter produces, so a wizard-driven
        turn feeds the same recommendation engine as a chat-driven one.

        `usage`/`priority`/a cargo need all land in `priorities` rather
        than dedicated fields - `StructuredRequirements` has no such
        fields (see `doc/api-contract.md`), and the recommendation
        engine's scoring already treats `priorities` as free-form tags,
        the same as the ones the AI extracts from chat text. Brand
        preference and annual mileage aren't filterable fields either;
        they're recorded in `notes` so they're visible in the
        requirements drawer, not silently dropped, but the recommendation
        engine does not currently act on them.

        Returns:
            Only the fields with a corresponding answer are populated;
            skipped questions leave their field at its default (`None`/
            empty), the same as an AI extraction that didn't mention them.
        """
        priorities = [value for value in (self.usage, self.priority) if value]
        if self.cargo_need and self.cargo_need != "none":
            priorities.append("cargo")

        notes_parts = []
        if self.brand_pref.strip():
            notes_parts.append(t("wizard.notes.brandPref", value=self.brand_pref.strip()))
        if self.annual_km is not None:
            notes_parts.append(t("wizard.notes.annualKm", km=self.annual_km))

        return StructuredRequirements(
            body_type=self.body_type,
            min_seats=self.seats,
            budget_max=Money(amount=self.budget, currency="CZK") if self.budget is not None else None,
            fuel_type=self.fuel_pattern,
            drivetrain=Drivetrain.awd if self.needs_awd else None,
            priorities=priorities,
            notes="; ".join(notes_parts) or None,
        )


@dataclass
class CatalogState:
    """ "Browsing mode" - the paginated full catalog shown before the AI
    has narrowed anything. Mirrors `catalogStore` + `useCatalog`.
    """

    cars: list[VehicleSummary] = field(default_factory=list)
    page: int = 0
    page_size: int = PAGE_SIZE
    total: int = 0
    is_loading: bool = False
    is_loading_more: bool = False
    error: bool = False
    # Catalog-browsing filters (see `app/ui/components/filter_bar.py`) -
    # pushed straight to the backend query rather than applied client-side,
    # the same way `price_asc`/`price_desc`/`alpha` sort does, so `total`
    # and pagination stay correct against the filtered set.
    brand_id: int | None = None
    fuel_type: FuelType | None = None
    drivetrain: Drivetrain | None = None
    brands: list[BrandRead] = field(default_factory=list)
    # The page's likes - listed first in the default ("Doporučeno") order,
    # see `catalog.list_vehicles`'s `preferred_model_ids`.
    liked: LikedModelsState | None = None
    # The likes as they were at `load_first_page`, reused by every
    # `load_more` - liking a card mid-scroll must not reshuffle the order
    # later pages are fetched in (that would duplicate or skip cars).
    _preferred_model_ids: frozenset[int] = frozenset()

    @property
    def has_more(self) -> bool:
        """True if `load_more` would return anything - `cars` loaded so
        far is fewer than `total` matching rows.
        """
        return len(self.cars) < self.total

    async def load_brands(self) -> None:
        """Loads the brand list once, for the manufacturer filter dropdown.
        Leaves `brands` empty (rather than raising) if the query fails -
        the filter bar just shows no brand options in that case.
        """

        def _load() -> object:
            with ui_db.get_session() as db:
                return catalog.list_brands(db)

        try:
            self.brands = await run.io_bound(_load)
        except Exception:
            self.brands = []

    async def load_first_page(self, sort: str | None) -> None:
        """(Re)loads page 1, replacing whatever's currently loaded -
        called on first mount and whenever `sort` or a filter changes.

        Args:
            sort: Backend sort option (`"price_asc"` | `"price_desc"` |
                `"alpha"`), or `None` for the default order.
        """
        self.is_loading = True
        self.error = False
        self._preferred_model_ids = _liked_ids(self.liked)

        def _load() -> object:
            with ui_db.get_session() as db:
                return catalog.list_vehicles(
                    db,
                    brand_id=self.brand_id,
                    fuel_type=self.fuel_type,
                    drivetrain=self.drivetrain,
                    sort=sort,
                    preferred_model_ids=self._preferred_model_ids,
                    page=1,
                    page_size=self.page_size,
                )

        try:
            result = await run.io_bound(_load)
            self.cars = result.items
            self.page = result.page
            self.total = result.total
        except Exception:
            self.error = True
        finally:
            self.is_loading = False

    async def load_more(self, sort: str | None) -> None:
        """Appends the next page to what's already loaded. No-ops if
        already loading another page or everything is already loaded.

        Args:
            sort: Same backend sort option as the initial load - must
                match, or the appended page could be in a different order.
        """
        if self.is_loading_more or not self.has_more:
            return
        self.is_loading_more = True
        next_page = self.page + 1

        def _load() -> object:
            with ui_db.get_session() as db:
                return catalog.list_vehicles(
                    db,
                    brand_id=self.brand_id,
                    fuel_type=self.fuel_type,
                    drivetrain=self.drivetrain,
                    sort=sort,
                    preferred_model_ids=self._preferred_model_ids,
                    page=next_page,
                    page_size=self.page_size,
                )

        try:
            result = await run.io_bound(_load)
            self.cars = [*self.cars, *result.items]
            self.page = result.page
            self.total = result.total
        except Exception:
            self.error = True
        finally:
            self.is_loading_more = False


@dataclass
class CompareState:
    """The cars picked for side-by-side comparison (at most
    `MAX_COMPARE`), in pick order.

    Kept in `storage` - `app.storage.user` in the app, so the pick survives
    reloads and is shared by the browser's tabs, the same way the custom
    sort order is. Each entry also carries its display label, so the
    compare tray can name the cars without a DB round-trip.
    """

    storage: MutableMapping = field(default_factory=dict)

    STORAGE_KEY = "compare_selection"

    @property
    def items(self) -> list[tuple[int, str]]:
        """`(configuration_id, label)` per picked car, in pick order."""
        return [(int(entry["id"]), str(entry["label"])) for entry in self.storage.get(self.STORAGE_KEY, [])]

    @property
    def ids(self) -> list[int]:
        return [configuration_id for configuration_id, _ in self.items]

    @property
    def is_full(self) -> bool:
        return len(self.items) >= MAX_COMPARE

    def contains(self, configuration_id: int) -> bool:
        return configuration_id in self.ids

    def _save(self, items: list[tuple[int, str]]) -> None:
        # A new list (not an in-place edit), so a persistent storage dict
        # notices the change and writes it out.
        self.storage[self.STORAGE_KEY] = [{"id": configuration_id, "label": label} for configuration_id, label in items]

    def add(self, configuration_id: int, label: str) -> bool:
        """Picks a car, unless it's already picked or the pick is full.

        Args:
            configuration_id: The car's configuration.
            label: Name to show for it (brand, model, trim).

        Returns:
            Whether the car is picked afterwards.
        """
        if self.contains(configuration_id):
            return True
        if self.is_full:
            return False
        self._save([*self.items, (configuration_id, label)])
        return True

    def remove(self, configuration_id: int) -> None:
        self._save([item for item in self.items if item[0] != configuration_id])

    def toggle(self, configuration_id: int, label: str) -> bool:
        """Unpicks a picked car, picks an unpicked one (if there's room).

        Returns:
            Whether the car is picked afterwards.
        """
        if self.contains(configuration_id):
            self.remove(configuration_id)
            return False
        return self.add(configuration_id, label)

    def replace(self, items: list[tuple[int, str]]) -> None:
        """Replaces the whole pick (e.g. with a model's trims), keeping at
        most `MAX_COMPARE`."""
        self._save(items[:MAX_COMPARE])

    def clear(self) -> None:
        self._save([])


async def fetch_comparison(configuration_ids: list[int]) -> list[VehicleDetail]:
    """Loads full detail for each picked car.

    Args:
        configuration_ids: The cars, in column order.

    Returns:
        Detail for every car that still exists and has a price, in the
        same order - a car dropped from the catalog since it was picked is
        simply left out.
    """

    def _load() -> list[VehicleDetail]:
        with ui_db.get_session() as db:
            found, _missing = catalog.compare_vehicles(db, configuration_ids)
            return found

    return await run.io_bound(_load)


async def fetch_trim_alternatives(configuration_id: int) -> list[TrimChoice]:
    """See `catalog.list_trim_alternatives`."""

    def _load() -> list[TrimChoice]:
        with ui_db.get_session() as db:
            return catalog.list_trim_alternatives(db, configuration_id)

    return await run.io_bound(_load)


async def fetch_vehicle_detail(configuration_id: int) -> VehicleDetail | None:
    """Loads full detail for one vehicle configuration.

    Args:
        configuration_id: Id of the configuration to load.

    Returns:
        The detail, or `None` if the id doesn't exist or has no current
        price (mirrors `catalog.get_vehicle_detail`'s own `None` case).
    """

    def _load() -> VehicleDetail | None:
        with ui_db.get_session() as db:
            return catalog.get_vehicle_detail(db, configuration_id)

    return await run.io_bound(_load)


async def create_shared_snapshot(
    requirements: list[UserRequirement], vehicles: list[VehicleSummary], user_id: int | None
) -> SharedSnapshot:
    """Stores a read-only snapshot for a shared link (see `app/services/sharing.py`).

    Args:
        requirements: Requirement lines to include.
        vehicles: Cars to include, in display order.
        user_id: The sharing user, if logged in.

    Returns:
        The stored snapshot, with the token for its link.
    """

    def _create() -> SharedSnapshot:
        with ui_db.get_session() as db:
            return sharing.create(db, requirements, vehicles, user_id)

    return await run.io_bound(_create)


async def fetch_shared_snapshot(token: str) -> SharedSnapshot | None:
    """Args:
        token: The token from a shared link.

    Returns:
        The snapshot, or `None` if unknown or expired.
    """

    def _load() -> SharedSnapshot | None:
        with ui_db.get_session() as db:
            return sharing.get(db, token)

    return await run.io_bound(_load)

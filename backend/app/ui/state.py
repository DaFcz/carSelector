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
from dataclasses import dataclass, field

from nicegui import run

from app.ai.errors import AiProviderError
from app.models.enums import Drivetrain, FuelType
from app.schemas.catalog import BrandRead
from app.schemas.common import Money
from app.schemas.requirement import StructuredRequirements, UserRequirement
from app.schemas.vehicle import VehicleDetail, VehicleSummary
from app.services import catalog
from app.services.conversation import orchestrator
from app.ui import db as ui_db

# Mirrors frontend/src/types/conversation.ts's ChatMessage.
ChatMessage = tuple[str, str]  # (role, text) - role is "user" | "assistant"

logger = logging.getLogger(__name__)

PAGE_SIZE = 20


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

    async def begin(self) -> None:
        """Starts a new conversation and seeds the transcript with its
        opening message. `start_conversation` is pure in-memory
        (uuid + dict), so this calls it directly rather than through
        `run.io_bound`.
        """
        self.is_loading = True
        self.error = None
        try:
            conversation_id, intro_message = orchestrator.start_conversation()
            self.conversation_id = conversation_id
            self.messages = [("assistant", intro_message)]
        except Exception:
            self.error = "unknown_error"
        finally:
            self.is_loading = False

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

        def _send() -> object:
            with ui_db.get_session() as db:
                return orchestrator.handle_message(db, conversation_id, trimmed)

        try:
            result = await run.io_bound(_send)
            self.messages.append(("assistant", result.assistant_text))
            self.requirements = result.requirements
            self.cars = result.vehicles
            self.has_narrowed = self.has_narrowed or result.searched
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

        def _send() -> object:
            with ui_db.get_session() as db:
                return orchestrator.handle_wizard_answers(db, conversation_id, requirements, summary_message)

        try:
            result = await run.io_bound(_send)
            self.messages.append(("assistant", result.assistant_text))
            self.requirements = result.requirements
            self.cars = result.vehicles
            self.has_narrowed = True
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
        """Abandons the current conversation and starts a fresh one."""
        self.conversation_id = None
        self.messages = []
        self.requirements = []
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
            notes_parts.append(f"Preference značky: {self.brand_pref.strip()}")
        if self.annual_km is not None:
            notes_parts.append(f"Roční nájezd přibližně {self.annual_km} km")

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
    """"Browsing mode" - the paginated full catalog shown before the AI
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

        def _load() -> object:
            with ui_db.get_session() as db:
                return catalog.list_vehicles(
                    db,
                    brand_id=self.brand_id,
                    fuel_type=self.fuel_type,
                    drivetrain=self.drivetrain,
                    sort=sort,
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

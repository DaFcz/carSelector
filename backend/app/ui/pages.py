"""The app's single page - port of frontend/src/pages/ChatPage.tsx (plus
`App.tsx`/`main.tsx`, which had nothing else to port: no router, no other
routed screens).
"""

import asyncio
import logging
from dataclasses import dataclass

from nicegui import app, ui
from nicegui.events import GenericEventArguments

from app.ai.client import is_configured
from app.models.enums import Drivetrain, FuelType
from app.schemas.requirement import StructuredRequirements
from app.schemas.vehicle import VehicleSummary
from app.ui.auth import AuthState, client_ip
from app.ui.compare import MAX_COMPARE, MIN_COMPARE
from app.ui.components.api_key_dialog import api_key_dialog
from app.ui.components.author_request_dialog import author_request_dialog
from app.ui.components.chat_column import chat_column
from app.ui.components.compare_dialog import compare_dialog, trim_picker_dialog
from app.ui.components.feedback_dialog import feedback_dialog
from app.ui.components.filter_bar import filter_bar
from app.ui.components.header import app_header
from app.ui.components.login_dialog import login_dialog
from app.ui.components.requirements_drawer import requirements_drawer
from app.ui.components.results_grid import (
    CompareToggles,
    LikeButtons,
    append_car_cards,
    results_grid,
    sort_control,
)
from app.ui.components.share_dialog import share_dialog
from app.ui.components.vehicle_detail_modal import vehicle_detail_modal
from app.ui.components.wizard import wizard_dialog
from app.ui.i18n import LANGUAGES, STRINGS, current_language, set_language, t, t_count
from app.ui.sort import BACKEND_SORT_OPTIONS, sort_cars
from app.ui.state import (
    PAGE_SIZE,
    CatalogState,
    CompareState,
    ConversationState,
    LikedModelsState,
    WizardState,
    create_shared_snapshot,
)
from app.ui.styles import register_styles

CUSTOM_ORDER_KEY = "custom_car_order"


def error_message(error: str, is_admin: bool = True) -> str:
    """User-facing text for a `ConversationState.error` code - specific for
    the AI failures (`ai_not_configured` and every `AiProviderError.code`),
    the generic one for anything else.

    `is_admin` matters for `ai_invalid_key`: the fix (the account menu's
    "AI klíč" item) is admin-only, so everyone else gets text that doesn't
    point at a control they can't see."""
    if error == "ai_not_configured":
        return t("chat.aiNotConfigured")
    if error == "ai_invalid_key" and not is_admin:
        return t("chat.errors.ai_invalid_key_user")
    if error in STRINGS["chat"]["errors"]:
        return t(f"chat.errors.{error}")
    return t("chat.genericError")


@dataclass
class _SortState:
    """Page-local UI state that never needs to survive a restart - the
    direct analogue of `ChatPage`'s own `useState`s (not modeled in
    `ConversationState`/`CatalogState`, which are the ported Zustand
    stores).
    """

    option: str = "recommended"


@dataclass
class _NarrowedPaging:
    """How many of `conv.cars` are currently rendered, for narrowed
    (AI/wizard) results - these arrive as one already-complete, already-
    ranked list (unlike `catalog_state.cars`, which is fetched page by
    page from the backend), so "load more" here means revealing more of
    what's already in memory, not another network round-trip. Reset to
    `PAGE_SIZE` on every new search (see `reset` and its call sites) so
    a fresh search starts from one page's worth of cards again."""

    shown: int = PAGE_SIZE

    def reset(self) -> None:
        self.shown = PAGE_SIZE


@dataclass
class _ResultsGridRef:
    """Holds the current `results_grid` container across `results_body()`
    rebuilds, so `on_results_scroll` can append later pages into the grid
    that's actually on screen right now instead of the one from whenever
    it was captured - `results_body()` reruns (and returns a brand new
    container) on every filter/sort/narrow change, not just once.
    """

    row: ui.row | None = None


@dataclass
class _MobileState:
    """Page-local layout state that only matters below the `md` breakpoint
    (768px) - on wider screens the chat and results columns sit side by
    side and the results controls are always shown, whatever these say.

    - `tab`: which single panel a phone shows - `"chat"` or `"results"`
      (switched by the bottom tab bar, see `mobile_tabs` in `index`).
    - `controls_open`: whether the sort/filter controls are expanded
      above the results - collapsed by default so they don't push the
      card list off a phone screen.
    """

    tab: str = "chat"
    controls_open: bool = False


# Hides an element below `md` only; the `!` is needed to beat nicegui.css's
# unlayered `display: flex` on rows/columns (see app/ui/styles.py).
MOBILE_HIDDEN = "max-md:hidden!"

# `viewport-fit=cover` exposes the `env(safe-area-inset-*)` values the
# bottom tab bar pads itself with; `interactive-widget=resizes-content`
# makes Android Chrome shrink the page (not overlay it) when the on-screen
# keyboard opens, keeping the chat input in view.
logger = logging.getLogger(__name__)

MOBILE_VIEWPORT = "width=device-width, initial-scale=1, viewport-fit=cover, interactive-widget=resizes-content"


@ui.page("/", viewport=MOBILE_VIEWPORT)
async def index() -> None:
    """Builds the whole app for one browser connection - NiceGUI gives
    each connection its own call of this function with private local
    state (see `app/ui/state.py`'s module docstring), the direct analogue
    of one mounted React tree.

    Event handlers are all defined before any UI is built: the
    refreshable render functions built further down (`chrome`/
    `results_header`/`results_body`/`drawer`) are invoked once
    immediately, synchronously, to draw the initial page - and their
    bodies pass these handlers to child components as plain values
    (button callbacks), which requires the names to already be bound.
    The handlers' own bodies are free to reference `chrome`/
    `results_header`/`results_body`/`drawer`/`chat_refresh` even though
    those are defined later, since a handler body only actually runs
    later too (on a click, well after page construction has finished).
    """
    register_styles()

    # Awaited before anything is built so the header renders the right
    # login/admin controls on first paint instead of flashing the anonymous
    # ones until a later refresh.
    auth_state = AuthState()
    await auth_state.refresh()

    conv = ConversationState(language=current_language())
    conv.user_id = auth_state.user.id if auth_state.is_logged_in else None
    conv.client_ip = client_ip()
    # Loaded before anything is built, like `auth_state`, so the first
    # catalog page and the first render already know the user's likes.
    liked = LikedModelsState(user_id=conv.user_id)
    await liked.load()
    conv.liked = liked
    catalog_state = CatalogState(liked=liked)
    # Both load only after the page is sent (see the end of this
    # function); until then the first render shows their loading states.
    conv.is_loading = True
    catalog_state.is_loading = True
    like_buttons = LikeButtons(liked.is_liked, liked.toggle)
    # Remembered per browser, like the custom sort order.
    compare_state = CompareState(storage=app.storage.user)
    wizard_state = WizardState()
    sort_state = _SortState()
    narrowed_paging = _NarrowedPaging()
    mobile_state = _MobileState()
    results_grid_ref = _ResultsGridRef()

    def custom_order() -> list[int]:
        return app.storage.user.get(CUSTOM_ORDER_KEY, [])

    def backend_sort() -> str | None:
        if conv.has_narrowed:
            return None
        return sort_state.option if sort_state.option in BACKEND_SORT_OPTIONS else None

    def displayed_cars() -> list[VehicleSummary]:
        """Every current match, sorted - the true count (used for the
        results-header title) and, for browsing mode, also exactly what's
        rendered (`catalog_state.cars` is itself only as many rows as have
        been fetched so far). Narrowed mode renders fewer than this -
        see `visible_cars`."""
        base_cars = conv.cars if conv.has_narrowed else catalog_state.cars
        client_sort = (
            "custom" if sort_state.option == "custom" else (sort_state.option if conv.has_narrowed else "recommended")
        )
        return sort_cars(base_cars, client_sort, custom_order())

    def visible_cars() -> list[VehicleSummary]:
        """What `results_body` actually renders. Browsing mode already
        only ever holds as many rows as fetched (`displayed_cars` itself
        is the visible set); narrowed mode gets everything back from
        `recommend()` in one go (see `RecommendationEngine.recommend`'s
        own docstring for why it's no longer capped at 10), so it's sliced
        client-side to `narrowed_paging.shown` instead - see
        `on_results_scroll`."""
        cars = displayed_cars()
        return cars[: narrowed_paging.shown] if conv.has_narrowed else cars

    open_share = share_dialog()

    async def share(cars: list[VehicleSummary]) -> None:
        """Stores a read-only snapshot of `cars` (plus the current
        requirements) and shows its link - see `app/services/sharing.py`."""
        try:
            snapshot = await create_shared_snapshot(conv.requirements, cars, conv.user_id)
        except Exception:
            logger.exception("Creating a shared snapshot failed")
            ui.notify(t("share.error"), type="negative")
            return
        open_share(snapshot)

    async def share_results() -> None:
        await share(displayed_cars())

    async def share_vehicle(detail: VehicleSummary) -> None:
        # The card's own summary carries what the detail lacks (match
        # score, AI explanation) - fall back to the detail itself when
        # the car isn't among the current results.
        card = next((car for car in displayed_cars() if car.configuration_id == detail.configuration_id), None)
        await share(
            [card or VehicleSummary.model_validate(detail.model_dump(include=set(VehicleSummary.model_fields)))]
        )

    def toggle_compare(car: VehicleSummary) -> bool:
        """Flips a car's place in the comparison pick (cards' and the
        detail's toggle) - refusing, with a note, once 4 are picked."""
        was_picked = compare_state.contains(car.configuration_id)
        picked = compare_state.toggle(car.configuration_id, f"{car.brand} {car.model} {car.trim}")
        if not was_picked and not picked:
            ui.notify(t("compare.full", max=MAX_COMPARE))
        on_compare_changed()
        return picked

    def on_compare_changed() -> None:
        compare_toggles.sync()
        compare_tray.refresh()

    compare_toggles = CompareToggles(compare_state.contains, toggle_compare)

    def match_scores() -> dict[int, int]:
        """Match scores of the current recommendation, for the comparison's
        "Shoda" row - none while just browsing the catalog."""
        if not conv.has_narrowed:
            return {}
        return {car.configuration_id: car.match_score for car in conv.cars if car.match_score is not None}

    # The dialogs below reference each other (comparison -> detail ->
    # trim picker -> comparison), hence the late-bound wrappers.
    async def open_detail_for(configuration_id: int) -> None:
        await open_detail(configuration_id)

    async def open_comparison_now() -> None:
        await open_comparison()

    async def open_comparison_after_picker() -> None:
        on_compare_changed()
        await open_comparison()

    open_trim_picker = trim_picker_dialog(compare_state, open_comparison_after_picker)
    open_detail = vehicle_detail_modal(share_vehicle, compare_state.contains, toggle_compare, open_trim_picker)
    open_comparison = compare_dialog(compare_state, on_compare_changed, open_detail_for, share, match_scores)

    async def start_comparison() -> None:
        if len(compare_state.ids) < MIN_COMPARE:
            ui.notify(t("compare.needTwo"))
            return
        await open_comparison_now()

    def remove_from_comparison(configuration_id: int) -> None:
        compare_state.remove(configuration_id)
        on_compare_changed()

    def clear_comparison() -> None:
        compare_state.clear()
        on_compare_changed()

    def refresh_all() -> None:
        chrome.refresh()
        refresh_results()
        loading_more_indicator.refresh()
        drawer.refresh()
        chat_refresh()

    async def send(text: str) -> None:
        await conv.send(text)
        narrowed_paging.reset()
        refresh_all()

    async def finish_wizard(requirements: StructuredRequirements, summary_message: str) -> None:
        await conv.send_wizard_answers(requirements, summary_message)
        narrowed_paging.reset()
        # The wizard is a "just show me cars" path - on a phone, land on
        # the results rather than on the chat summary it leaves behind.
        set_mobile_tab("results")
        refresh_all()

    open_wizard_dialog = wizard_dialog(wizard_state, finish_wizard)

    def on_api_key_changed() -> None:
        conv.error = None  # a "not configured" banner may be stale now
        refresh_all()

    # Admin-only (the key is process-wide): the header hides the button from
    # everyone else, and the dialog re-checks at click time regardless.
    open_api_key_dialog = api_key_dialog(on_api_key_changed, lambda: auth_state.is_admin)

    def on_logged_in() -> None:
        # Either saves whatever's already been built up anonymously this
        # session under the account that just logged in, or - if nothing
        # has been gathered yet this session - restores that account's
        # previously saved requirements. See ConversationState.on_login.
        conv.user_id = auth_state.user.id if auth_state.user else None
        liked.user_id = conv.user_id
        if conv.user_id is not None:

            async def _apply_login() -> None:
                # Likes first: a restored-requirements search inside
                # `conv.on_login()` should already rank by the merged set.
                await liked.on_login()
                await conv.on_login()
                # Only the restore branch can actually change cars/
                # messages/requirements (persisting saves what's already
                # on screen, unchanged) - refreshing regardless is
                # harmless and keeps this from silently missing a case.
                narrowed_paging.reset()
                refresh_all()

            asyncio.ensure_future(_apply_login())
        chrome.refresh()

    open_login_dialog = login_dialog(auth_state, on_logged_in)
    open_author_request_dialog = author_request_dialog(auth_state)
    open_feedback_dialog = feedback_dialog(
        auth_state,
        "search",
        lambda: None if conv.structured_requirements == StructuredRequirements() else conv.structured_requirements,
    )

    def logout() -> None:
        auth_state.logout()
        # Stops this (now-anonymous) session from continuing to save its
        # requirements under the account that just logged out.
        conv.user_id = None
        liked.on_logout()
        chrome.refresh()
        refresh_results()  # empty the hearts that belonged to the account

    def switch_language() -> None:
        """Flips between the supported languages and reloads, so every
        already-built element (dialogs included) is rebuilt in the new one
        and a fresh conversation starts in it. A logged-in user's saved
        requirements are restored by the reload; an anonymous chat in
        progress starts over."""
        language = current_language()
        set_language(LANGUAGES[(LANGUAGES.index(language) + 1) % len(LANGUAGES)])
        ui.navigate.reload()

    def open_wizard() -> None:
        wizard_state.open_wizard()
        open_wizard_dialog()

    async def restart() -> None:
        await conv.restart()
        narrowed_paging.reset()
        await catalog_state.load_first_page(backend_sort())
        refresh_all()

    async def toggle_drawer() -> None:
        conv.toggle_drawer()
        drawer.refresh()

    async def close_drawer() -> None:
        conv.close_drawer()
        drawer.refresh()

    async def change_sort(value: str) -> None:
        sort_state.option = value
        if not conv.has_narrowed and value in BACKEND_SORT_OPTIONS:
            await catalog_state.load_first_page(value)
        else:
            narrowed_paging.reset()  # new order - start revealing from the top again, same as browsing's re-fetch
        refresh_results()

    # How close to the bottom (px) of the scrollable results column
    # triggers the next page - far enough that the fetch has a chance to
    # land before the user actually hits the end (cards are ~350px tall,
    # so this is roughly two rows of lead time).
    _LOAD_MORE_THRESHOLD_PX = 600

    async def on_results_scroll(event: GenericEventArguments) -> None:
        """Infinite scroll: replaces the old "Load more" button - fires
        on every scroll of the results column (throttled, see `.on(...)`
        below) and reveals more results once the user nears the bottom.
        Two sources, same reveal mechanism (`append_car_cards`, see below):

        - Browsing mode fetches the next page from the backend
          (`catalog_state.load_more`) - its own `is_loading_more`/
          `has_more` guard (see app/ui/state.py) is what actually prevents
          duplicate/overlapping fetches, since scroll events arrive as a
          burst of separate async tasks but each one's guard check runs
          synchronously before any `await`, so only the first of a burst
          ever gets past it.
        - Narrowed (AI/wizard) mode already has every match in memory
          (`conv.cars` - see `RecommendationEngine.recommend`'s own
          docstring for why it's no longer capped at 10) - "loading more"
          here just raises `narrowed_paging.shown` and reveals the next
          slice, no backend call needed.

        Either way, the newly-revealed cars are appended into the existing
        grid container (`append_car_cards`) rather than going through a
        full `results_body.refresh()` - refreshing would re-render every
        card accumulated so far, not just the new ones, and once enough
        pile up that single re-render's message exceeds NiceGUI's ~1MB
        websocket limit and disconnects the client (exactly the failure
        mode a large budget-only match set would otherwise hit).
        `results_body.refresh()` is still used as a fallback for the
        "Moje pořadí" custom-sort grid, whose drag handling is only wired
        up once per full render (see `results_grid`/`append_car_cards`'s
        docstrings) - the header (title/sort/filters) never needs it here,
        since revealing more already-fetched/already-known results changes
        neither the reported total nor the filters.
        """
        metrics = event.args or {}
        distance_to_bottom = (
            metrics.get("scrollHeight", 0) - metrics.get("scrollTop", 0) - metrics.get("clientHeight", 0)
        )
        if distance_to_bottom > _LOAD_MORE_THRESHOLD_PX:
            return

        if conv.has_narrowed:
            all_cars = displayed_cars()
            shown_before = narrowed_paging.shown
            if shown_before >= len(all_cars):
                return
            narrowed_paging.shown = min(shown_before + PAGE_SIZE, len(all_cars))
            new_cars = all_cars[shown_before : narrowed_paging.shown]
            if results_grid_ref.row is not None and sort_state.option != "custom" and new_cars:
                append_car_cards(
                    results_grid_ref.row,
                    new_cars,
                    lambda car: open_detail(car.configuration_id),
                    like_buttons,
                    compare_toggles,
                )
            else:
                results_body.refresh()
            return

        if not catalog_state.has_more or catalog_state.is_loading_more:
            return

        # Kick the load off as its own task and yield once so its
        # synchronous prefix (setting `is_loading_more = True`) actually
        # runs before this function's own refresh below - otherwise the
        # spinner would never get a chance to render.
        cars_before = len(catalog_state.cars)
        load_task = asyncio.ensure_future(catalog_state.load_more(backend_sort()))
        await asyncio.sleep(0)
        loading_more_indicator.refresh()
        await load_task
        loading_more_indicator.refresh()

        new_cars = catalog_state.cars[cars_before:]
        if results_grid_ref.row is not None and sort_state.option != "custom" and new_cars:
            append_car_cards(
                results_grid_ref.row,
                new_cars,
                lambda car: open_detail(car.configuration_id),
                like_buttons,
                compare_toggles,
            )
        else:
            results_body.refresh()

    async def change_brand(brand_id: int | None) -> None:
        catalog_state.brand_id = brand_id
        await catalog_state.load_first_page(backend_sort())
        refresh_results()

    async def change_fuel_type(fuel_type: FuelType | None) -> None:
        catalog_state.fuel_type = fuel_type
        await catalog_state.load_first_page(backend_sort())
        refresh_results()

    async def change_drivetrain(drivetrain: Drivetrain | None) -> None:
        catalog_state.drivetrain = drivetrain
        await catalog_state.load_first_page(backend_sort())
        refresh_results()

    def reorder(order: list[int]) -> None:
        app.storage.user[CUSTOM_ORDER_KEY] = order
        refresh_results()

    def refresh_results() -> None:
        """Refreshes both halves of the results column (see the split
        between `results_header` and `results_body` below) - every call
        site that used to just refresh the old single `results` needs
        both, since a filter/sort change can affect the title/count text
        (header) as well as the grid itself (body). Also the mobile tab
        bar, whose "Výsledky" tab shows the same count."""
        results_header.refresh()
        results_body.refresh()
        mobile_tabs.refresh()

    def results_count() -> int:
        return len(displayed_cars()) if conv.has_narrowed else catalog_state.total

    def set_mobile_tab(tab: str) -> None:
        """Switches which panel a phone shows. CSS-only (`MOBILE_HIDDEN`):
        both panels stay built and keep their state (chat scroll position,
        loaded result pages), and desktop ignores it entirely."""
        mobile_state.tab = tab
        if tab == "chat":
            chat_panel.classes(remove=MOBILE_HIDDEN)
            results_panel.classes(add=MOBILE_HIDDEN)
        else:
            chat_panel.classes(add=MOBILE_HIDDEN)
            results_panel.classes(remove=MOBILE_HIDDEN)
        mobile_tabs.refresh()

    def toggle_mobile_controls() -> None:
        mobile_state.controls_open = not mobile_state.controls_open
        results_header.refresh()

    with ui.column().classes("relative flex h-[100dvh] w-full flex-col overflow-hidden bg-bg text-text gap-0"):

        @ui.refreshable
        def chrome() -> None:
            app_header(
                len(conv.requirements),
                restart,
                toggle_drawer,
                open_wizard,
                is_configured(),
                open_api_key_dialog,
                auth_state.user,
                open_login_dialog,
                logout,
                switch_language,
                open_author_request_dialog,
                open_feedback_dialog,
            )

        chrome()

        # `overflow-clip`, not `-hidden`: the closed requirements drawer
        # sits just off-screen (`translate-x-full`), and an `overflow:
        # hidden` box can still be scrolled sideways (by focus/tap), which
        # on a phone slid the whole layout left.
        with ui.row().classes("relative flex min-h-0 flex-1 w-full flex-nowrap gap-0 overflow-clip"):
            # Phones show one of these two panels at a time (see
            # `set_mobile_tab`); chat first, since it's the app's main
            # entry point.
            with ui.column().classes("h-full w-full md:w-auto shrink-0 gap-0").mark("chat-panel") as chat_panel:
                chat_refresh = chat_column(conv, send)

            with (
                ui.column()
                .classes(f"min-w-0 h-full flex-1 flex flex-col overflow-hidden gap-0 {MOBILE_HIDDEN}")
                .mark("results-panel") as results_panel
            ):

                @ui.refreshable
                def results_header() -> None:
                    # Title/sort/filters - kept OUTSIDE the scrollable
                    # column below (a `shrink-0` sibling above it, not
                    # part of its scrolled content) so they stay in view
                    # while only the card grid scrolls underneath.
                    cars = displayed_cars()
                    # Sort/filters collapse behind a toggle on phones only.
                    controls_hidden = "" if mobile_state.controls_open else MOBILE_HIDDEN

                    with ui.row().classes("mb-3 md:mb-4.5 w-full flex-wrap items-start justify-between gap-3"):
                        with ui.column().classes("gap-0 max-md:min-w-0 max-md:flex-1"):
                            if conv.has_narrowed:
                                title = t_count("results.title", len(cars))
                            elif catalog_state.is_loading:
                                title = t("results.loadingTitle")
                            else:
                                title = t_count("results.browsingTitle", catalog_state.total)
                            ui.label(title).classes("text-[17px] md:text-[19px] font-bold text-text")
                            ui.label(t("results.updated") if conv.has_narrowed else t("results.startPrompt")).classes(
                                "mt-0.5 text-[13px] text-subtext"
                            )
                        if cars:
                            ui.button(t("share.button"), icon="share", on_click=share_results).props(
                                "flat no-caps"
                            ).classes(
                                "shrink-0 rounded-control border border-border bg-panel-2 px-3 py-1.5 text-[13px] "
                                "font-semibold text-text"
                            ).mark("share-results")
                        ui.button(
                            t("results.controlsToggle"),
                            icon="tune",
                            on_click=toggle_mobile_controls,
                        ).props("flat no-caps").classes(
                            "shrink-0 rounded-control border px-3 py-1.5 text-[13px] font-semibold md:hidden! "
                            + (
                                "border-accent bg-accent-soft text-accent"
                                if mobile_state.controls_open
                                else "border-border bg-panel-2 text-text"
                            )
                        )
                        with ui.row().classes(f"gap-0 max-md:w-full {controls_hidden}").mark("sort-controls"):
                            sort_control(sort_state.option, change_sort)

                    if not conv.has_narrowed:
                        with ui.column().classes(f"w-full gap-0 {controls_hidden}"):
                            filter_bar(
                                catalog_state.brands,
                                catalog_state.brand_id,
                                catalog_state.fuel_type,
                                catalog_state.drivetrain,
                                change_brand,
                                change_fuel_type,
                                change_drivetrain,
                            )

                    if conv.error is not None:
                        message = error_message(conv.error, auth_state.is_admin)
                        ui.label(message).classes(
                            "mb-4 w-full rounded-control bg-flag-bg px-3.5 py-2.5 text-[13px] text-flag"
                        )

                with ui.column().classes("w-full shrink-0 px-4 pt-4 md:px-7 md:pt-6 gap-0"):
                    results_header()

                with (
                    ui.column()
                    .classes("min-h-0 min-w-0 flex-1 overflow-y-auto px-4 pb-4 md:px-7 md:pb-6 gap-0")
                    .on(
                        "scroll",
                        on_results_scroll,
                        throttle=0.2,
                        js_handler=(
                            "(event) => emit({"
                            "scrollTop: event.target.scrollTop, "
                            "scrollHeight: event.target.scrollHeight, "
                            "clientHeight: event.target.clientHeight"
                            "})"
                        ),
                    )
                ):

                    @ui.refreshable
                    def results_body() -> None:
                        has_results = len(displayed_cars()) > 0
                        show_catalog_error = not conv.has_narrowed and catalog_state.error and not has_results
                        show_catalog_loading = not conv.has_narrowed and catalog_state.is_loading

                        if show_catalog_loading:
                            ui.label(t("results.loadingCatalog")).classes(
                                "w-full px-5 py-10 text-center text-[13px] text-subtext"
                            )
                        elif show_catalog_error:
                            ui.label(t("results.catalogError")).classes(
                                "w-full px-5 py-10 text-center text-[13px] text-subtext"
                            )
                        else:
                            reorderable = sort_state.option == "custom"
                            results_grid_ref.row = results_grid(
                                visible_cars(),
                                lambda car: open_detail(car.configuration_id),
                                reorderable,
                                reorder if reorderable else None,
                                like_buttons,
                                compare_toggles,
                            )

                    results_body()

                    @ui.refreshable
                    def loading_more_indicator() -> None:
                        # Infinite scroll (see on_results_scroll) replaces the
                        # old "Load more" button - this is just the in-flight
                        # indicator for the fetch it triggers. Refreshed on its
                        # own (not as part of `results_body()`) since it needs
                        # to toggle far more often than the grid itself changes.
                        if not conv.has_narrowed and catalog_state.is_loading_more:
                            with ui.row().classes("mt-4 w-full items-center justify-center gap-2"):
                                ui.spinner(size="1.25rem")
                                ui.label(t("results.loadingMore")).classes("text-[13px] text-subtext")

                    loading_more_indicator()

                @ui.refreshable
                def compare_tray() -> None:
                    """The comparison pick, pinned under the results (outside
                    their scroll area) - only while something is picked."""
                    items = compare_state.items
                    if not items:
                        return
                    with (
                        ui.row()
                        .classes(
                            "w-full shrink-0 flex-nowrap items-center justify-between gap-3 border-t border-border "
                            "bg-panel px-4 py-2.5 md:px-7"
                        )
                        .mark("compare-tray")
                    ):
                        # Phones: just the count - named pills don't fit.
                        ui.label(t("compare.trayCount", count=len(items))).classes(
                            "text-[13px] font-semibold text-text md:hidden!"
                        )
                        with ui.row().classes("min-w-0 flex-wrap items-center gap-1.5 max-md:hidden!"):
                            ui.label(t("compare.trayTitle")).classes(
                                "text-[11.5px] font-bold uppercase tracking-wide text-subtext"
                            )
                            for configuration_id, label in items:
                                with ui.row().classes(
                                    "flex-nowrap items-center gap-0.5 rounded-full border border-border bg-panel-2 "
                                    "py-0.5 pl-2.5 pr-0.5 text-[12px] text-text"
                                ):
                                    ui.label(label).classes("max-w-[180px] truncate")
                                    ui.button(
                                        icon="close", on_click=lambda c=configuration_id: remove_from_comparison(c)
                                    ).props("flat round dense size=xs").classes("text-subtext").tooltip(
                                        t("compare.remove")
                                    )
                        with ui.row().classes("shrink-0 flex-nowrap items-center gap-2"):
                            ui.button(t("compare.clear"), on_click=clear_comparison).props(
                                "flat dense no-caps"
                            ).classes("text-[12.5px] text-subtext")
                            ui.button(
                                t("compare.open", count=len(items)), icon="compare_arrows", on_click=start_comparison
                            ).props("no-caps unelevated").classes(
                                "rounded-control bg-accent px-3 py-1.5 text-[13px] font-semibold text-accent-text"
                            ).mark("compare-open")

                compare_tray()

            @ui.refreshable
            def drawer() -> None:
                requirements_drawer(conv.requirements, conv.drawer_open, close_drawer)

            drawer()

        @ui.refreshable
        def mobile_tabs() -> None:
            """Bottom tab bar, phones only - switches between the chat and
            results panels (see `set_mobile_tab`). Pads itself by the iOS
            home-indicator safe area (see `MOBILE_VIEWPORT`)."""
            with ui.row().classes(
                "w-full shrink-0 flex-nowrap gap-0 border-t border-border bg-panel "
                "pb-[env(safe-area-inset-bottom)] md:hidden!"
            ):
                tabs = [
                    ("chat", "forum", t("mobileTabs.chat")),
                    ("results", "directions_car", f"{t('mobileTabs.results')} ({results_count()})"),
                ]
                for key, icon, label in tabs:
                    active = mobile_state.tab == key
                    ui.button(label, icon=icon, on_click=lambda key=key: set_mobile_tab(key)).props(
                        "flat no-caps stack"
                    ).classes(
                        "min-h-14 flex-1 rounded-none py-1.5 text-[12px] font-semibold "
                        + ("text-accent" if active else "text-subtext")
                    )

        mobile_tabs()

    # Everything below can be slow - for a logged-in user `conv.begin()`
    # rebuilds the saved result, which asks the AI for one explanation per
    # car. NiceGUI only sends the page once this function returns (or
    # awaits `connected()`), and fails it with a 500 after
    # `response_timeout` (3 s), so send the page first - showing the
    # loading states set above - and load into it afterwards.
    try:
        await ui.context.client.connected()
    except TimeoutError:
        return  # the browser never connected - nobody to load for
    await conv.begin()
    await catalog_state.load_brands()
    await catalog_state.load_first_page(backend_sort())
    refresh_all()

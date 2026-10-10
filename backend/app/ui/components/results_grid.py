"""Port of frontend/src/components/ResultsGrid.tsx + CarCard.tsx + SortControl.tsx."""

from collections.abc import Awaitable, Callable

from nicegui import ui

from app.schemas.vehicle import VehicleSummary
from app.ui.i18n import t
from app.ui.money import format_money
from app.ui.sort import SORT_OPTIONS

DRAG_HANDLE_CLASS = "drag-handle"


class LikeButtons:
    """The heart (like) button on every result card, kept in sync per car
    *model*: liking one card of a model fills the heart on every rendered
    card of that model, since a like targets the model, not the
    configuration (see `app/models/liked_model.py`).

    One instance per page (see `app/ui/pages.py`) - it outlives every
    `results_grid` rebuild, so it keeps a registry of the buttons currently
    on screen per model and prunes the ones a rebuild deleted.
    """

    def __init__(self, is_liked: Callable[[int], bool], on_toggle: Callable[[int], Awaitable[bool]]) -> None:
        """Args:
        is_liked: Returns whether a model is currently liked - read
            when a card is rendered.
        on_toggle: Flips a model's like and returns the new state (see
            `LikedModelsState.toggle`).
        """
        self._is_liked = is_liked
        self._on_toggle = on_toggle
        self._buttons: dict[int, list[ui.button]] = {}

    @staticmethod
    def _apply(button: ui.button, liked: bool) -> None:
        button.props(f"icon={'favorite' if liked else 'favorite_border'}")
        button.props(f"aria-pressed={'true' if liked else 'false'}")
        button.classes(add="text-flag" if liked else "text-subtext", remove="text-subtext" if liked else "text-flag")

    def render(self, model_id: int) -> ui.button:
        """Builds the heart button for one card of `model_id`.

        Args:
            model_id: The `models` row the card belongs to.

        Returns:
            The button (already registered for syncing).
        """
        button = (
            # `color=None`: no Quasar `text-primary`, so the Tailwind
            # colors `_apply` sets actually show.
            ui.button(on_click=lambda: self._toggle(model_id), color=None)
            .props("flat round dense")
            .classes("bg-panel/85 shadow-card")
            .tooltip(t("car.like"))
            .mark(f"like-{model_id}")
        )
        # The card itself opens the detail on click - the heart must not.
        # A separate listener (not `on_click`) so the `.stop` modifier only
        # affects the browser's propagation, not how the click is handled.
        button.on("click.stop", js_handler="() => {}")
        self._apply(button, self._is_liked(model_id))
        self._buttons.setdefault(model_id, []).append(button)
        return button

    async def _toggle(self, model_id: int) -> None:
        liked = await self._on_toggle(model_id)
        alive = [button for button in self._buttons.get(model_id, []) if not button.is_deleted]
        self._buttons[model_id] = alive
        for button in alive:
            self._apply(button, liked)


class CompareToggles:
    """The "Porovnat" checkbox on every result card. Like `LikeButtons`,
    one instance per page that outlives `results_grid` rebuilds and keeps a
    registry of the toggles on screen, so `sync` can update them all when
    the pick changes elsewhere (the compare tray, the comparison dialog).
    """

    def __init__(self, is_picked: Callable[[int], bool], on_toggle: Callable[[VehicleSummary], bool]) -> None:
        """Args:
        is_picked: Whether a configuration is currently picked.
        on_toggle: Flips a car's pick and returns whether it's picked
            afterwards (see `CompareState.toggle`) - may refuse when the
            pick is full.
        """
        self._is_picked = is_picked
        self._on_toggle = on_toggle
        self._toggles: dict[int, list[ui.button]] = {}

    @staticmethod
    def _apply(button: ui.button, picked: bool) -> None:
        button.props(f"icon={'check_box' if picked else 'check_box_outline_blank'}")
        button.props(f"aria-pressed={'true' if picked else 'false'}")
        button.classes(
            add="text-accent" if picked else "text-subtext", remove="text-subtext" if picked else "text-accent"
        )

    def render(self, car: VehicleSummary) -> ui.button:
        """Builds the toggle for one card.

        Args:
            car: The card's car.

        Returns:
            The button (already registered for syncing).
        """
        button = (
            ui.button(t("compare.toggle"), on_click=lambda: self._toggle(car), color=None)
            .props("flat dense no-caps")
            .classes("-ml-1 px-1 text-[12px] font-semibold")
            .mark(f"compare-{car.configuration_id}")
        )
        # The card itself opens the detail on click - the toggle must not.
        button.on("click.stop", js_handler="() => {}")
        self._apply(button, self._is_picked(car.configuration_id))
        self._toggles.setdefault(car.configuration_id, []).append(button)
        return button

    def _toggle(self, car: VehicleSummary) -> None:
        self._on_toggle(car)
        self.sync()

    def sync(self) -> None:
        """Re-applies the current pick to every toggle still on screen."""
        for configuration_id, buttons in list(self._toggles.items()):
            alive = [button for button in buttons if not button.is_deleted]
            if alive:
                self._toggles[configuration_id] = alive
                for button in alive:
                    self._apply(button, self._is_picked(configuration_id))
            else:
                del self._toggles[configuration_id]


def sort_control(value: str, on_change: Callable[[str], None]) -> None:
    """Builds the "Seřadit podle" sort dropdown.

    Args:
        value: Currently selected sort option (one of `SORT_OPTIONS`).
        on_change: Called with the newly selected option's value.
    """
    options = {option: t(f"results.sort.{option}") for option in SORT_OPTIONS}
    with ui.row().classes("flex-nowrap items-center gap-2 text-[13px] text-subtext max-md:w-full"):
        ui.label(t("results.sortBy")).classes("max-md:w-28 max-md:shrink-0")
        ui.select(options, value=value, on_change=lambda e: on_change(e.value)).classes(
            "max-md:min-w-0 max-md:grow rounded-control border border-border bg-panel-2 px-2.5 py-1.5 text-[13px] font-semibold text-text"
        ).props("borderless dense options-dense")


def car_card(
    car: VehicleSummary,
    on_select: Callable[[VehicleSummary], None] | None,
    like: LikeButtons | None = None,
    compare: CompareToggles | None = None,
) -> None:
    """Renders one result card - make/model/trim, price, match score,
    spec tags, an optional flag/AI-explanation line, and the like heart.

    Args:
        car: Vehicle to render.
        on_select: Called with `car` when clicked/Enter-activated; the
            card is only interactive (clickable, focusable) when given.
        like: Renders the heart button over the photo, if given.
        compare: Renders the "Porovnat" checkbox at the card's foot, if given.
    """
    is_high_score = car.match_score is not None and car.match_score >= 90
    border_class = "border-accent" if car.top_pick else "border-border"
    with ui.column().classes(
        "relative w-full overflow-hidden rounded-card border bg-panel shadow-card animate-fade-in gap-0 "
        f"{border_class} {'cursor-pointer' if on_select else ''}"
    ) as card:
        if on_select is not None:
            card.props("tabindex=0").mark(f"car-{car.configuration_id}")
            card.on("click", lambda: on_select(car))
            card.on("keydown.enter", lambda: on_select(car))

        if car.top_pick:
            ui.label(t("car.topMatch")).classes(
                "absolute left-2.5 top-2.5 z-10 rounded-full bg-accent px-2.5 py-1 text-[10.5px] font-bold "
                "uppercase tracking-wide text-accent-text"
            )

        with (
            ui.element("div")
            .classes(
                "relative flex h-[110px] sm:h-[140px] w-full items-center justify-center px-3 text-center font-mono text-[11px] text-subtext"
            )
            .style(
                "background-image: repeating-linear-gradient(45deg, var(--color-panel-2), var(--color-panel-2) 10px, "
                "var(--color-border) 10px, var(--color-border) 20px)"
            )
        ):
            ui.label(t("car.photoPlaceholder", make=car.brand, model=car.model))
            if like is not None:
                like.render(car.model_id).classes("absolute bottom-2 right-2")

        with ui.column().classes("w-full gap-2.5 p-4 pt-3.5"):
            with ui.row().classes("w-full items-start justify-between gap-2"):
                with ui.column().classes("gap-0"):
                    ui.label(f"{car.brand} {car.model} {car.trim}").classes("text-[14.5px] font-bold text-text")
                    ui.label(format_money(car.price)).classes("text-[12.5px] text-subtext")
                if car.match_score is not None:
                    score_class = "bg-accent-soft text-accent" if is_high_score else "text-subtext"
                    ui.label(f"{car.match_score}%").classes(
                        f"shrink-0 rounded-full px-2.5 py-1 text-[15px] font-bold {score_class}"
                    )

            with ui.row().classes("w-full flex-wrap gap-1.5"):
                for spec in car.specs:
                    ui.label(spec).classes(
                        "rounded-full border border-border bg-panel-2 px-2.5 py-1 text-[11px] font-semibold text-subtext"
                    )

            if car.flag:
                ui.label(car.flag).classes("w-full rounded-control bg-flag-bg px-2.5 py-1.5 text-[11.5px] text-flag")

            if car.explanation:
                ui.label(car.explanation).classes("w-full text-[12px] italic leading-relaxed text-subtext")

            if compare is not None:
                compare.render(car)


def _card_slot(
    car: VehicleSummary,
    on_select: Callable[[VehicleSummary], None],
    reorderable: bool,
    like: LikeButtons | None = None,
    compare: CompareToggles | None = None,
) -> None:
    """Renders one card in its grid slot (the `relative w-[230px]` wrapper -
    full-width on phones - plus the optional drag handle) - the loop body shared by `results_grid`
    and `append_car_cards`.

    Args:
        car: Vehicle to render.
        on_select: Called when the card is clicked/activated.
        reorderable: Shows the "⠿" drag handle when true.
        like: Renders the card's like heart, if given.
        compare: Renders the card's compare toggle, if given.
    """
    with ui.column().classes("relative w-full sm:w-[230px] gap-0"):
        if reorderable:
            # The only drag handle (see `results_grid`'s `make_sortable`) -
            # bigger on touch screens, where it's a finger target.
            ui.label("⠿").classes(
                f"{DRAG_HANDLE_CLASS} absolute right-2 top-2 z-10 flex h-6 w-6 cursor-grab items-center "
                "justify-center rounded-full bg-panel-2/90 text-[13px] text-subtext "
                "pointer-coarse:h-10 pointer-coarse:w-10 pointer-coarse:text-[18px]"
            ).tooltip(t("results.dragHint"))
        car_card(car, on_select, like, compare)


def results_grid(
    cars: list[VehicleSummary],
    on_select: Callable[[VehicleSummary], None],
    reorderable: bool,
    on_reorder: Callable[[list[int]], None] | None,
    like: LikeButtons | None = None,
    compare: CompareToggles | None = None,
) -> ui.row | None:
    """Renders the responsive card grid, or an empty-state message.

    Cards are laid out as a wrapping flex row (fixed 230px card width,
    full width below the `sm` breakpoint)
    rather than the original CSS grid - visually equivalent for this
    fixed-size-card case, and avoids the sortable container needing a
    `display: grid` that plays awkwardly with `make_sortable`'s DOM
    reordering during drag.

    Args:
        cars: Cars to display, already sorted (see `app/ui/sort.py`).
        on_select: Called when a card is clicked/activated.
        reorderable: Enables drag-to-reorder ("Moje pořadí" sort mode),
            by each card's "⠿" handle only.
        on_reorder: Called with every card's configuration id in its new
            order once a drag completes. Required when `reorderable` is
            `True`.
        like: Renders each card's like heart, if given.
        compare: Renders each card's compare toggle, if given.

    Returns:
        The card row container, so a caller doing infinite-scroll paging
        (see `append_car_cards`) can append later pages into it without
        re-rendering the cards already on screen - or `None` if `cars`
        was empty and only the empty-state label was rendered.
    """
    if not cars:
        ui.label(t("results.emptyState")).classes("w-full px-5 py-10 text-center text-[13px] text-subtext")
        return None

    if reorderable:
        # Tooltips need hover - touch screens get the hint as plain text.
        # (`block!`: Quasar's own `.hidden` is `!important`.)
        ui.label(t("results.dragHintTouch")).classes("mb-3 hidden text-[12.5px] text-subtext pointer-coarse:block!")

    with ui.row().classes("w-full gap-4") as container:
        for car in cars:
            _card_slot(car, on_select, reorderable, like, compare)

    if reorderable and on_reorder is not None:
        order = [car.configuration_id for car in cars]

        def _on_end(event: object) -> None:
            # SortableEventArguments (nicegui.elements.mixins.sortable_element)
            # carries the drag's old/new position within this container.
            new_order = list(order)
            moved = new_order.pop(event.old_index)  # type: ignore[attr-defined]
            new_order.insert(event.new_index, moved)  # type: ignore[attr-defined]
            on_reorder(new_order)

        # Handle-only dragging: with the whole card draggable, a touch
        # swipe meant to scroll the results would reorder cards instead.
        container.make_sortable(handle=f".{DRAG_HANDLE_CLASS}", animation=0.15, on_end=_on_end)

    return container


def append_car_cards(
    container: ui.row,
    cars: list[VehicleSummary],
    on_select: Callable[[VehicleSummary], None],
    like: LikeButtons | None = None,
    compare: CompareToggles | None = None,
) -> None:
    """Appends more cards into an already-rendered `results_grid` container,
    for infinite-scroll paging - without this, loading the next page would
    mean calling `results_grid` again with the *whole* accumulated list,
    which re-sends every already-visible card over the websocket on every
    scroll tick. For a large catalog (hundreds of rows) that repeated
    full-rebuild eventually produces a single update message past
    NiceGUI's ~1MB websocket message limit, disconnecting the client (see
    doc/CHANGELOG.md's infinite-scroll message-size fix entry).

    Only used for non-reorderable grids (`app/ui/pages.py` falls back to a
    full `results_grid` re-render for the "Moje pořadí" custom-sort mode
    instead of calling this) - a reorderable grid's `make_sortable` drag
    handling is set up once in `results_grid` and appending outside that
    isn't worth the added risk for a rarely-combined edge case (dragging
    to reorder while still infinite-scrolling the full browsing catalog).

    Args:
        container: The `ui.row` a prior `results_grid` call returned.
        cars: Only the newly-loaded page's cars, in display order - not
            the full accumulated list.
        on_select: Same callback passed to the original `results_grid` call.
        like: Same `LikeButtons` passed to the original `results_grid` call.
        compare: Same `CompareToggles` passed to the original `results_grid` call.
    """
    with container:
        for car in cars:
            _card_slot(car, on_select, reorderable=False, like=like, compare=compare)

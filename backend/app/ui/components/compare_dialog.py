"""Side-by-side comparison of 2-4 picked cars, plus the trim picker that
fills the pick with one model's trims ("Porovnat výbavy" in the detail
dialog).

Both dialogs are built once per page, like the vehicle detail dialog (see
`app/ui/components/vehicle_detail_modal.py`); the returned functions open
them. The rows themselves come from `app/ui/compare.py`, shared with the
PDF export.
"""

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from nicegui import run, ui

from app.schemas.catalog import TrimChoice
from app.schemas.vehicle import VehicleDetail, VehicleSummary
from app.ui.compare import (
    MAX_COMPARE,
    MIN_COMPARE,
    MISSING,
    OPTIONAL,
    STANDARD,
    CompareRow,
    CompareSection,
    build_sections,
    default_trim_selection,
    same_brand,
    vehicle_title,
    visible_rows,
)
from app.ui.i18n import current_language, t, use_language
from app.ui.money import format_money
from app.ui.state import CompareState, fetch_comparison, fetch_trim_alternatives
from app.ui.vehicle_pdf import build_comparison_pdf, comparison_pdf_filename

logger = logging.getLogger(__name__)

_BUTTON_CLASSES = "rounded-control border border-border bg-panel-2 px-3 py-1.5 text-[13px] font-semibold text-text"
# Phones show the labels plus two cars at a time (the rest scroll
# sideways); wider screens give every car an equal share of the width.
_COLUMNS_PHONE = "104px repeat({count}, 132px)"
_COLUMNS_WIDE = "170px repeat({count}, minmax(170px, 1fr))"
_CELL = "border-b border-border px-3 py-2 text-[12.5px]"
# Sticky left column / top row: an opaque background, so scrolled cells
# don't show through.
_STICKY_LEFT = "sticky left-0 z-[1] bg-panel"
_KIND_CLASSES = {STANDARD: "text-text font-semibold", OPTIONAL: "text-text", MISSING: "text-subtext"}
_BEST_CLASSES = "bg-accent-soft text-accent font-bold"


def to_summary(detail: VehicleDetail) -> VehicleSummary:
    """Args:
        detail: A compared car.

    Returns:
        Its summary part - what sharing stores per car.
    """
    return VehicleSummary.model_validate(detail.model_dump(include=set(VehicleSummary.model_fields)))


@dataclass
class _CompareView:
    # Nothing is rendered until the first open - the dialog is built at
    # page load, closed, and its placeholder texts mustn't leak into it.
    opened: bool = False
    details: list[VehicleDetail] = field(default_factory=list)
    is_loading: bool = False
    error: bool = False
    differences_only: bool = True


def compare_dialog(
    compare: CompareState,
    on_changed: Callable[[], None],
    open_detail: Callable[[int], Awaitable[None]],
    on_share: Callable[[list[VehicleSummary]], Awaitable[None]],
    match_scores: Callable[[], dict[int, int]],
) -> Callable[[], Awaitable[None]]:
    """Builds the (initially closed) comparison dialog.

    Args:
        compare: The page's pick - removing a car here removes it there.
        on_changed: Called after the pick changes from inside the dialog,
            so the page can update the tray and the cards' toggles.
        open_detail: Opens a car's detail dialog.
        on_share: Shares the given cars (the existing share link).
        match_scores: AI match score per configuration id, from the
            current recommendation - empty while just browsing.

    Returns:
        A function that loads the current pick and opens the dialog.
    """
    view = _CompareView()

    with (
        ui.dialog().props("maximized") as dialog,
        ui.card().classes("h-full w-full max-w-none flex flex-col flex-nowrap gap-0 rounded-none bg-panel p-0"),
    ):

        async def _export_pdf() -> None:
            details = list(view.details)
            differences_only = view.differences_only
            scores = match_scores()
            # The worker thread can't see this browser's language choice.
            language = current_language()

            def _build() -> bytes:
                with use_language(language):
                    return build_comparison_pdf(details, differences_only, scores)

            try:
                content = await run.io_bound(_build)
            except Exception:
                logger.exception("Comparison PDF export failed")
                ui.notify(t("vehicleDetail.exportPdfError"), type="negative")
                return
            ui.download.content(content, comparison_pdf_filename(details), "application/pdf")

        async def _share() -> None:
            await on_share([to_summary(detail) for detail in view.details])

        def _toggle_differences(value: bool) -> None:
            view.differences_only = value
            _body.refresh()

        def _remove(configuration_id: int) -> None:
            compare.remove(configuration_id)
            view.details = [detail for detail in view.details if detail.configuration_id != configuration_id]
            on_changed()
            _toolbar.refresh()
            _body.refresh()

        async def _open_detail(configuration_id: int) -> None:
            dialog.close()
            await open_detail(configuration_id)

        @ui.refreshable
        def _toolbar() -> None:
            with ui.row().classes(
                "w-full shrink-0 flex-wrap items-center justify-between gap-3 border-b border-border px-4 py-3 md:px-6"
            ):
                with ui.column().classes("gap-0"):
                    ui.label(t("compare.title")).classes("text-[18px] font-bold text-text")
                    ui.label(t("compare.bestHint")).classes("text-[12px] text-subtext")
                with ui.row().classes("flex-wrap items-center gap-2"):
                    ui.switch(
                        t("compare.differencesOnly"),
                        value=view.differences_only,
                        on_change=lambda e: _toggle_differences(e.value),
                    ).props("dense color=primary").classes("text-[13px] text-text").mark("compare-differences")
                    if len(view.details) >= MIN_COMPARE:
                        ui.button(t("share.button"), icon="share", on_click=_share).props("flat no-caps").classes(
                            _BUTTON_CLASSES
                        ).mark("compare-share")
                        ui.button(t("vehicleDetail.exportPdf"), icon="picture_as_pdf", on_click=_export_pdf).props(
                            "flat no-caps"
                        ).classes(_BUTTON_CLASSES).mark("compare-pdf")
                    ui.button(t("vehicleDetail.close"), on_click=dialog.close).props("flat no-caps").classes(
                        _BUTTON_CLASSES
                    )

        _toolbar()

        @ui.refreshable
        def _body() -> None:
            if not view.opened:
                return
            if view.is_loading:
                ui.label(t("compare.loading")).classes("w-full px-5 py-10 text-center text-[13px] text-subtext")
                return
            if view.error:
                ui.label(t("compare.error")).classes("w-full px-5 py-10 text-center text-[13px] text-subtext")
                return
            if len(view.details) < MIN_COMPARE:
                ui.label(t("compare.tooFew")).classes("w-full px-5 py-10 text-center text-[13px] text-subtext")
                return
            _table(view.details, view.differences_only, match_scores(), _remove, _open_detail)

        # The one scroll container, both directions - so the car header row
        # (sticky top) and the label column (sticky left) both stay put.
        with ui.element("div").classes("min-h-0 w-full flex-1 overflow-auto"):
            _body()

    async def open_comparison() -> None:
        """Loads the current pick and opens the dialog."""
        view.opened = True
        view.details = []
        view.error = False
        view.is_loading = True
        dialog.open()
        _toolbar.refresh()
        _body.refresh()
        try:
            view.details = await fetch_comparison(compare.ids)
        except Exception:
            logger.exception("Loading the comparison failed")
            view.error = True
        finally:
            view.is_loading = False
            _toolbar.refresh()
            _body.refresh()

    return open_comparison


def _table(
    details: list[VehicleDetail],
    differences_only: bool,
    scores: dict[int, int],
    on_remove: Callable[[int], None],
    on_detail: Callable[[int], Awaitable[None]],
) -> None:
    """The comparison grid: a header row with the cars, then one block per
    section. A CSS grid rather than a table, so the header row and the
    label column can both be sticky.

    Args:
        details: The compared cars, one column each.
        differences_only: Hide rows where every car is the same.
        scores: AI match score per configuration id.
        on_remove: Removes a car from the comparison.
        on_detail: Opens a car's detail.
    """
    count = len(details)
    with (
        ui.element("div")
        .classes(
            "grid w-max min-w-full [grid-template-columns:var(--compare-phone)] "
            "md:[grid-template-columns:var(--compare-wide)]"
        )
        .style(
            f"--compare-phone: {_COLUMNS_PHONE.format(count=count)}; "
            f"--compare-wide: {_COLUMNS_WIDE.format(count=count)}"
        )
        .mark("compare-table")
    ):
        ui.element("div").classes(f"sticky left-0 top-0 z-[3] bg-panel {_CELL}")
        for detail in details:
            with (
                ui.column()
                .classes(f"sticky top-0 z-[2] gap-1 bg-panel {_CELL}")
                .mark(f"compare-column-{detail.configuration_id}")
            ):
                with ui.row().classes("w-full flex-nowrap items-start justify-between gap-1"):
                    ui.label(vehicle_title(detail)).classes(
                        "min-w-0 break-words text-[13px] md:text-[13.5px] font-bold leading-snug text-text"
                    )
                    ui.button(icon="close", on_click=lambda d=detail: on_remove(d.configuration_id)).props(
                        "flat round dense size=sm"
                    ).classes("shrink-0 text-subtext").tooltip(t("compare.remove")).mark(
                        f"compare-remove-{detail.configuration_id}"
                    )
                ui.label(format_money(detail.price)).classes("text-[12.5px] text-subtext")
                ui.button(t("compare.detail"), on_click=lambda d=detail: on_detail(d.configuration_id)).props(
                    "flat dense no-caps"
                ).classes("-ml-1 px-1 text-[12px] font-semibold text-accent")

        sections = build_sections(details, scores)
        # Colors always come last; with mixed brands the per-car equipment
        # lists go right before them, where the equipment rows would be.
        for section in sections[:-1]:
            _section(section, differences_only)
        if not same_brand(details):
            _per_car_equipment(details)
        _section(sections[-1], differences_only)


def _section(section: CompareSection, differences_only: bool) -> None:
    rows = visible_rows(section, differences_only)
    _section_heading(section.title)
    if not rows:
        with ui.element("div").classes(f"{_CELL} text-subtext").style("grid-column: 1 / -1"):
            ui.label(t("compare.noDifferences")).classes(_STICKY_LEFT)
        return
    for row in rows:
        _row(row)


def _per_car_equipment(details: list[VehicleDetail]) -> None:
    """Each car's equipment as its own collapsible lists - for cars of
    different brands, whose equipment names don't line up (see
    `app/ui/compare.py`'s `same_brand`)."""
    _section_heading(t("compare.sections.equipment"))
    with ui.element("div").classes(f"{_CELL} text-subtext").style("grid-column: 1 / -1"):
        ui.label(t("compare.perBrandNote")).classes(f"{_STICKY_LEFT} max-w-[90vw]")
    ui.element("div").classes(f"{_STICKY_LEFT} {_CELL}")
    for detail in details:
        with ui.column().classes(f"gap-1 {_CELL}"):
            with (
                ui.expansion(t("compare.standardCount", count=len(detail.standard_equipment)))
                .props("dense")
                .classes("w-full text-[12.5px]")
            ):
                for item in detail.standard_equipment:
                    ui.label(f"• {item}").classes("text-[12px] text-text")
            with (
                ui.expansion(t("compare.optionalCount", count=len(detail.optional_equipment)))
                .props("dense")
                .classes("w-full text-[12.5px]")
            ):
                for option in detail.optional_equipment:
                    ui.label(f"• {option.name} · {format_money(option.surcharge)}").classes("text-[12px] text-text")


def _section_heading(title: str) -> None:
    with ui.element("div").classes("border-b border-border bg-panel-2 px-3 py-1.5").style("grid-column: 1 / -1"):
        ui.label(title).classes("sticky left-3 w-max text-[11.5px] font-bold uppercase tracking-wide text-subtext")


def _row(row: CompareRow) -> None:
    ui.label(row.label).classes(f"{_STICKY_LEFT} {_CELL} text-subtext")
    for index, cell in enumerate(row.cells):
        classes = _BEST_CLASSES if index in row.best else _KIND_CLASSES.get(cell.kind, "text-text")
        ui.label(cell.text).classes(f"{_CELL} {classes}")


@dataclass
class _PickerView:
    opened: bool = False  # see `_CompareView.opened`
    choices: list[TrimChoice] = field(default_factory=list)
    ticked: set[int] = field(default_factory=set)
    is_loading: bool = False
    error: bool = False


def trim_picker_dialog(
    compare: CompareState, on_confirm: Callable[[], Awaitable[None]]
) -> Callable[[int], Awaitable[None]]:
    """Builds the (initially closed) "which trims to compare" dialog.

    Args:
        compare: The page's pick - confirming replaces it with the
            ticked trims.
        on_confirm: Awaited after the pick is replaced (the page then
            updates the tray/toggles and opens the comparison).

    Returns:
        A function that loads a configuration's model trims and opens the
        dialog.
    """
    view = _PickerView()

    with (
        ui.dialog() as dialog,
        ui.card().classes("w-full max-w-[480px] rounded-card border border-border bg-panel p-4 md:p-6 shadow-card"),
    ):

        def _toggle(index: int, value: bool) -> None:
            if value and index not in view.ticked and len(view.ticked) >= MAX_COMPARE:
                ui.notify(t("compare.full", max=MAX_COMPARE))
            elif value:
                view.ticked.add(index)
            else:
                view.ticked.discard(index)
            _content.refresh()

        async def _confirm() -> None:
            if len(view.ticked) < MIN_COMPARE:
                ui.notify(t("compare.needTwo"))
                return
            picked = [view.choices[index] for index in sorted(view.ticked)]
            compare.replace([(choice.vehicle.configuration_id, _label(choice.vehicle)) for choice in picked])
            dialog.close()
            await on_confirm()

        @ui.refreshable
        def _content() -> None:
            if not view.opened:
                return
            ui.label(t("compare.trimPicker.title")).classes("text-[17px] font-bold text-text")
            if view.is_loading:
                ui.label(t("compare.trimPicker.loading")).classes("py-6 text-[13px] text-subtext")
                return
            if view.error or len(view.choices) < MIN_COMPARE:
                ui.label(t("compare.error") if view.error else t("compare.trimPicker.single")).classes(
                    "py-4 text-[13px] text-subtext"
                )
                ui.button(t("compare.trimPicker.cancel"), on_click=dialog.close).props("flat no-caps").classes(
                    _BUTTON_CLASSES
                )
                return

            ui.label(t("compare.trimPicker.hint", max=MAX_COMPARE)).classes("text-[12.5px] text-subtext")
            with ui.column().classes("mt-3 w-full gap-1.5"):
                for index, choice in enumerate(view.choices):
                    with ui.row().classes(
                        "w-full flex-nowrap items-center gap-2 rounded-control border border-border px-2 py-1.5"
                    ):
                        ui.checkbox(value=index in view.ticked, on_change=lambda e, i=index: _toggle(i, e.value)).props(
                            "dense"
                        ).mark(f"trim-{choice.trim_id}")
                        with ui.column().classes("min-w-0 flex-1 gap-0"):
                            name = choice.trim_name
                            if choice.is_current:
                                name += f" ({t('compare.trimPicker.current')})"
                            ui.label(name).classes("text-[13px] font-semibold text-text")
                            engine = "sameEngine" if choice.same_engine else "otherEngine"
                            ui.label(t(f"compare.trimPicker.{engine}")).classes("text-[11.5px] text-subtext")
                        ui.label(format_money(choice.vehicle.price)).classes("shrink-0 text-[12.5px] text-subtext")

            with ui.row().classes("mt-4 w-full items-center justify-between gap-2"):
                ui.label(t("compare.trimPicker.selected", count=len(view.ticked), max=MAX_COMPARE)).classes(
                    "text-[12.5px] text-subtext"
                )
                with ui.row().classes("gap-2"):
                    ui.button(t("compare.trimPicker.cancel"), on_click=dialog.close).props("flat no-caps").classes(
                        _BUTTON_CLASSES
                    )
                    ui.button(t("compare.trimPicker.confirm"), on_click=_confirm).props("no-caps unelevated").classes(
                        "rounded-control bg-accent px-3.5 py-1.5 text-[13px] font-semibold text-accent-text"
                    ).mark("trim-picker-confirm")

        _content()

    async def open_for(configuration_id: int) -> None:
        """Loads the trims of `configuration_id`'s model and opens the
        picker, with the current trim and the closest in price ticked."""
        view.opened = True
        view.choices = []
        view.ticked = set()
        view.error = False
        view.is_loading = True
        dialog.open()
        _content.refresh()
        try:
            view.choices = await fetch_trim_alternatives(configuration_id)
            current = next((i for i, choice in enumerate(view.choices) if choice.is_current), 0)
            view.ticked = default_trim_selection([choice.vehicle.price.amount for choice in view.choices], current)
        except Exception:
            logger.exception("Loading trims for configuration %s failed", configuration_id)
            view.error = True
        finally:
            view.is_loading = False
            _content.refresh()

    return open_for


def _label(car: VehicleSummary) -> str:
    return f"{car.brand} {car.model} {car.trim}"

"""Port of frontend/src/components/VehicleDetailModal.tsx.

Built once per page (not inside a page-wide refreshable) so the dialog
element persists across unrelated page refreshes - the returned `open_for`
function is what callers (see `app/ui/pages.py`) invoke on a card click.
Backdrop-click and Escape-to-close come for free from `ui.dialog`'s
default (non-`persistent`) behavior.
"""

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from nicegui import run, ui

from app.schemas.vehicle import VehicleDetail
from app.ui.i18n import current_language, t, use_language
from app.ui.money import format_money
from app.ui.state import fetch_vehicle_detail
from app.ui.vehicle_format import co2_label, consumption_label, power_label
from app.ui.vehicle_pdf import build_vehicle_pdf, pdf_filename

logger = logging.getLogger(__name__)


@dataclass
class _ModalState:
    detail: VehicleDetail | None = None
    is_loading: bool = False
    error: bool = False


def _detail_field(label: str, value: str | None) -> None:
    """One label/value pair in the powertrain grid, falling back to a
    "no data" placeholder when `value` is `None`.

    Args:
        label: Field label.
        value: Field value, or `None` if not available for this vehicle.
    """
    with ui.column().classes("gap-0"):
        ui.label(label).classes("text-[10.5px] font-bold uppercase tracking-wide text-subtext")
        ui.label(value if value is not None else t("vehicleDetail.fields.noData")).classes(
            "mt-0.5 font-semibold text-text"
        )


def vehicle_detail_modal(
    on_share: Callable[[VehicleDetail], Awaitable[None]] | None = None,
    is_compared: Callable[[int], bool] | None = None,
    on_toggle_compare: Callable[[VehicleDetail], bool] | None = None,
    on_compare_trims: Callable[[int], Awaitable[None]] | None = None,
) -> Callable[[int], None]:
    """Builds the (initially closed) vehicle detail dialog.

    Args:
        on_share: Called with the shown vehicle when its "Sdílet" button
            is clicked; no button without it.
        is_compared: Whether a configuration is in the comparison pick -
            drives the "Přidat k porovnání" toggle's look.
        on_toggle_compare: Adds/removes the shown vehicle to/from the
            comparison pick; no toggle without it.
        on_compare_trims: Opens the trim picker for the shown vehicle's
            model ("Porovnat výbavy"); no button without it.

    Returns:
        A function to call with a configuration id to load and open it.
    """
    state = _ModalState()

    # `dialog-mobile-full` (see app/ui/styles.py): fullscreen on phones.
    with (
        ui.dialog().classes("dialog-mobile-full") as dialog,
        ui.card().classes(
            "max-h-[85vh] w-full max-w-[640px] overflow-y-auto rounded-card border border-border bg-panel p-4 md:p-6 "
            "shadow-card animate-fade-in"
        ),
    ):

        async def _export_pdf() -> None:
            """Renders the shown vehicle as a PDF (off the event loop - see
            `app/ui/vehicle_pdf.py`) and hands it to the browser as a download."""
            detail = state.detail
            if detail is None:
                return
            try:
                # The worker thread can't see this browser's language choice.
                language = current_language()

                def _build() -> bytes:
                    with use_language(language):
                        return build_vehicle_pdf(detail)

                content = await run.io_bound(_build)
            except Exception:
                logger.exception("PDF export failed for configuration %s", detail.configuration_id)
                ui.notify(t("vehicleDetail.exportPdfError"), type="negative")
                return
            ui.download.content(content, pdf_filename(detail), "application/pdf")

        async def _compare_trims(configuration_id: int) -> None:
            dialog.close()
            if on_compare_trims is not None:
                await on_compare_trims(configuration_id)

        @ui.refreshable
        def _content() -> None:
            if state.is_loading:
                ui.label(t("vehicleDetail.loading")).classes("w-full px-5 py-10 text-center text-[13px] text-subtext")
                return
            if state.error or state.detail is None:
                ui.label(t("vehicleDetail.error")).classes("w-full px-5 py-10 text-center text-[13px] text-subtext")
                return

            detail = state.detail
            # Sticky header: the card itself is the scroll container, so the
            # title and the buttons stay pinned to its top while the specs
            # scroll underneath. The negative margins pull the header's
            # background over the card's padding, so no text shows through
            # beside it. The negative `top` does the same above it: a sticky
            # element's offset is measured from inside the scroll container's
            # padding, so `top-0` would leave a padding-high gap.
            with (
                ui.row()
                .classes(
                    "sticky -top-4 md:-top-6 z-10 -mx-4 -mt-4 w-[calc(100%+2rem)] flex-wrap items-start justify-between gap-3 "
                    "border-b border-border bg-panel px-4 pb-3 pt-4 "
                    "md:-mx-6 md:-mt-6 md:w-[calc(100%+3rem)] md:px-6 md:pt-6"
                )
                .mark("vehicle-detail-header")
            ):
                with ui.column().classes("gap-0"):
                    ui.label(f"{detail.brand} {detail.model} {detail.trim}").classes("text-[18px] font-bold text-text")
                    ui.label(format_money(detail.price)).classes("mt-0.5 text-[14px] text-subtext")
                    with ui.row().classes("mt-1 flex-wrap items-center gap-1"):
                        if on_toggle_compare is not None:
                            picked = is_compared is not None and is_compared(detail.configuration_id)

                            def _toggle_compare() -> None:
                                on_toggle_compare(detail)
                                _content.refresh()

                            ui.button(
                                t("compare.added") if picked else t("compare.add"),
                                icon="check_box" if picked else "check_box_outline_blank",
                                on_click=_toggle_compare,
                            ).props("flat dense no-caps").classes(
                                "-ml-1 px-1 text-[12.5px] font-semibold "
                                + ("text-accent" if picked else "text-subtext")
                            ).mark("detail-compare")
                        if on_compare_trims is not None:
                            ui.button(
                                t("compare.compareTrims"),
                                icon="compare_arrows",
                                on_click=lambda: _compare_trims(detail.configuration_id),
                            ).props("flat dense no-caps").classes("px-1 text-[12.5px] font-semibold text-subtext").mark(
                                "detail-compare-trims"
                            )
                with ui.row().classes("shrink-0 items-center gap-2"):
                    if on_share is not None:
                        ui.button(t("share.button"), icon="share", on_click=lambda: on_share(detail)).props(
                            "flat no-caps"
                        ).classes(
                            "rounded-control border border-border bg-panel-2 px-3 py-1.5 text-[13px] font-semibold text-text"
                        ).mark("share-vehicle")
                    ui.button(t("vehicleDetail.exportPdf"), icon="picture_as_pdf", on_click=_export_pdf).props(
                        "flat no-caps"
                    ).classes(
                        "rounded-control border border-border bg-panel-2 px-3 py-1.5 text-[13px] font-semibold text-text"
                    ).mark("export-pdf")
                    ui.button(t("vehicleDetail.close"), on_click=dialog.close).props("flat no-caps").classes(
                        "rounded-control border border-border bg-panel-2 px-3 py-1.5 text-[13px] font-semibold text-text"
                    )

            with ui.column().classes("mt-5 w-full gap-2"):
                ui.label(t("vehicleDetail.sections.powertrain")).classes(
                    "text-[13px] font-bold uppercase tracking-wide text-subtext"
                )
                with ui.grid(columns=2).classes(
                    "w-full gap-x-4 gap-y-2.5 rounded-control bg-panel-2 p-3.5 text-[13px]"
                ):
                    pt = detail.powertrain
                    _detail_field(
                        t("vehicleDetail.fields.fuelType"), t(f"vehicleDetail.enums.fuelType.{pt.fuel_type.value}")
                    )
                    _detail_field(
                        t("vehicleDetail.fields.drivetrain"), t(f"vehicleDetail.enums.drivetrain.{pt.drivetrain.value}")
                    )
                    _detail_field(t("vehicleDetail.fields.transmission"), pt.transmission)
                    _detail_field(t("vehicleDetail.fields.power"), power_label(pt))
                    _detail_field(t("vehicleDetail.fields.consumption"), consumption_label(pt))
                    _detail_field(t("vehicleDetail.fields.co2"), co2_label(pt))

            with ui.column().classes("mt-5 w-full gap-2"):
                ui.label(t("vehicleDetail.sections.colors")).classes(
                    "text-[13px] font-bold uppercase tracking-wide text-subtext"
                )
                if not detail.colors:
                    ui.label(t("vehicleDetail.noColors")).classes("text-[12.5px] text-subtext")
                else:
                    with ui.row().classes("w-full flex-wrap gap-1.5"):
                        for color in detail.colors:
                            parts = [color.name]
                            if color.finish_type is not None:
                                parts.append(t(f"vehicleDetail.enums.colorFinish.{color.finish_type.value}"))
                            label = " · ".join(parts)
                            if color.surcharge.amount > 0:
                                label += f" · +{format_money(color.surcharge)}"
                            ui.label(label).classes(
                                "rounded-full border border-border bg-panel-2 px-2.5 py-1 text-[11.5px] "
                                "font-semibold text-subtext"
                            )

            with ui.column().classes("mt-5 w-full gap-2"):
                ui.label(t("vehicleDetail.sections.standardEquipment")).classes(
                    "text-[13px] font-bold uppercase tracking-wide text-subtext"
                )
                with ui.grid().classes("w-full grid-cols-1 sm:grid-cols-2 gap-x-4 gap-y-1 text-[12.5px] text-text"):
                    for item in detail.standard_equipment:
                        ui.label(f"• {item}")

            with ui.column().classes("mt-5 w-full gap-2"):
                ui.label(t("vehicleDetail.sections.optionalEquipment")).classes(
                    "text-[13px] font-bold uppercase tracking-wide text-subtext"
                )
                if not detail.optional_equipment:
                    ui.label(t("vehicleDetail.noOptionalEquipment")).classes("text-[12.5px] text-subtext")
                else:
                    with ui.column().classes("w-full gap-1.5"):
                        for option in detail.optional_equipment:
                            with ui.row().classes("w-full items-center justify-between gap-3 text-[12.5px]"):
                                ui.label(
                                    f"{option.name} ({t(f'vehicleDetail.enums.optionCategory.{option.category.value}')})"
                                ).classes("text-text")
                                ui.label(format_money(option.surcharge)).classes("shrink-0 text-subtext")

            with ui.column().classes("mt-5 w-full gap-2"):
                ui.label(t("vehicleDetail.sections.priceHistory")).classes(
                    "text-[13px] font-bold uppercase tracking-wide text-subtext"
                )
                with ui.column().classes("w-full gap-1.5"):
                    for point in detail.price_history:
                        with ui.row().classes("w-full items-center justify-between gap-3 text-[12.5px]"):
                            valid_to = (
                                point.valid_to.isoformat()
                                if point.valid_to
                                else t("vehicleDetail.priceHistory.current")
                            )
                            ui.label(f"{point.valid_from.isoformat()} – {valid_to}").classes("text-subtext")
                            price_text = format_money(point.price)
                            if point.lowest_price_30d is not None:
                                price_text += (
                                    " ("
                                    + t(
                                        "vehicleDetail.priceHistory.lowestPrice30d",
                                        price=format_money(point.lowest_price_30d),
                                    )
                                    + ")"
                                )
                            ui.label(price_text).classes("text-text")

        _content()

    async def open_for(configuration_id: int) -> None:
        """Loads and opens the modal for one vehicle configuration.

        Args:
            configuration_id: Id of the configuration to show.
        """
        state.detail = None
        state.error = False
        state.is_loading = True
        dialog.open()
        _content.refresh()
        try:
            detail = await fetch_vehicle_detail(configuration_id)
            if detail is None:
                state.error = True
            else:
                state.detail = detail
        except Exception:
            state.error = True
        finally:
            state.is_loading = False
            _content.refresh()

    return open_for

"""Port of frontend/src/components/RequirementsDrawer.tsx.

Renders as a slide-in overlay - the caller (see `app/ui/pages.py`) must
place it inside a `position: relative` container alongside the chat/
results columns, matching the original's `<div className="relative flex
min-h-0 flex-1">` wrapper.
"""

from collections.abc import Callable

from nicegui import ui

from app.schemas.requirement import UserRequirement
from app.ui.i18n import t


def requirements_drawer(requirements: list[UserRequirement], open_: bool, on_close: Callable[[], None]) -> None:
    """Builds the backdrop + slide-in requirements panel.

    Args:
        requirements: Cards to list, one per populated `StructuredRequirements` field.
        open_: Whether the drawer is currently shown.
        on_close: Called when the backdrop or the close button is clicked.
    """
    backdrop_classes = "absolute inset-0 z-10 transition-colors " + (
        "pointer-events-auto bg-black/25" if open_ else "pointer-events-none bg-transparent"
    )
    ui.element("div").classes(backdrop_classes).on("click", on_close)

    panel_classes = (
        "absolute inset-y-0 right-0 z-20 w-full md:w-[360px] overflow-y-auto border-l border-border bg-panel p-4 md:p-[22px] "
        "shadow-card transition-transform duration-300 ease-out "
    ) + ("translate-x-0" if open_ else "translate-x-full")

    with ui.column().classes(panel_classes + " gap-0"):
        with ui.row().classes("w-full flex-nowrap items-start justify-between gap-3"):
            ui.label(t("header.technicalRequirements")).classes("text-[16px] font-bold text-text")
            # Explicit close: on mobile the panel is full-width, leaving no
            # backdrop to tap.
            ui.button(t("requirements.close"), on_click=on_close).props("flat no-caps").classes(
                "shrink-0 rounded-control border border-border bg-panel-2 px-3 py-1.5 text-[13px] font-semibold "
                "text-text"
            )
        ui.label(t("requirements.subtitle")).classes("mb-2 text-[12.5px] text-subtext")

        if not requirements:
            ui.label(t("requirements.empty")).classes("w-full px-1 py-10 text-center text-[13px] text-subtext")
            return

        for req in requirements:
            card_classes = "w-full border-b border-border px-1 py-3 gap-0" + (" animate-flash" if req.changed else "")
            with ui.column().classes(card_classes):
                ui.label(req.label).classes("text-[11px] font-bold uppercase tracking-wide text-subtext")
                ui.label(req.value).classes("mt-0.5 text-[14px] font-semibold text-text")
                ui.label(req.source).classes("mt-1 text-[12px] italic text-subtext")

"""Port of frontend/src/components/AppHeader.tsx."""

from collections.abc import Callable

from nicegui import ui

from app.ui.i18n import t


def app_header(
    requirements_count: int,
    on_restart: Callable[[], None],
    on_toggle_drawer: Callable[[], None],
    on_open_wizard: Callable[[], None],
    ai_configured: bool,
    on_open_api_key: Callable[[], None],
) -> None:
    """Builds the top bar: brand/tagline on the left, restart + wizard +
    requirements-drawer toggle on the right.

    Args:
        requirements_count: Shown as a badge on the drawer-toggle button.
        on_restart: Called when "Restartovat" is clicked.
        on_toggle_drawer: Called when the requirements button is clicked.
        on_open_wizard: Called when "Průvodce výběrem" is clicked - opens
            the guided question-by-question alternative to the free-text
            chat (see `app/ui/components/wizard.py`).
        ai_configured: Whether an AI API key is set - switches the API-key
            button between its plain and "missing" (highlighted) look.
        on_open_api_key: Called when the API-key button is clicked - opens
            `app/ui/components/api_key_dialog.py`.
    """
    with ui.row().classes("shrink-0 items-center justify-between border-b border-border px-7 py-4.5 w-full"):
        with ui.column().classes("gap-0.5"):
            ui.label(t("header.brand")).classes("text-xl font-bold tracking-tight text-text")
            ui.label(t("header.tagline")).classes("text-[12.5px] text-subtext")

        with ui.row().classes("items-center gap-2.5"):
            ui.link("Admin", "/admin").classes("text-[12.5px] text-subtext underline-offset-2 hover:underline")
            ui.button(
                t("header.apiKey") if ai_configured else t("header.apiKeyMissing"),
                icon="key",
                on_click=on_open_api_key,
            ).props("flat no-caps").classes(
                "rounded-control border px-3.5 py-2 text-[13px] "
                + ("border-border text-subtext" if ai_configured else "border-flag bg-flag-bg text-flag")
            )
            ui.button(t("header.startWizard"), on_click=on_open_wizard).props("no-caps unelevated").classes(
                "rounded-control bg-accent px-3.5 py-2 text-[13px] font-semibold text-accent-text"
            )
            ui.button(t("header.restart"), on_click=on_restart).props("flat no-caps").classes(
                "rounded-control border border-border px-3.5 py-2 text-[13px] text-subtext"
            )
            with ui.button(on_click=on_toggle_drawer).props("flat no-caps").classes(
                "flex items-center gap-2 rounded-control border border-border bg-panel-2 px-3.5 py-2 "
                "text-[13px] font-semibold text-text"
            ):
                ui.label(t("header.technicalRequirements"))
                ui.label(str(requirements_count)).classes(
                    "rounded-full bg-accent px-[7px] py-0.5 text-[11px] font-bold text-accent-text"
                )

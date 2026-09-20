"""Dialog for entering the AI provider's API key at runtime, so it never
has to live in source code (or, if the operator prefers, in `.env`
either). The key goes to `app.ai.client.set_runtime_api_key` - process
memory only, see there.
"""

from collections.abc import Callable

from nicegui import ui

from app.ai.client import InvalidApiKeyError, is_configured, set_runtime_api_key
from app.core.config import AI_PROVIDER
from app.ui.i18n import t

_PROVIDER_LABELS = {"groq": ("Groq", "console.groq.com"), "anthropic": ("Anthropic", "console.anthropic.com")}


def api_key_dialog(on_changed: Callable[[], None]) -> Callable[[], None]:
    """Builds the (initially closed) API-key dialog.

    The saved key is never shown back - the input always starts empty; the
    dialog only reports whether a key is currently set.

    Args:
        on_changed: Called after the key was saved or cleared, so the
            caller (see `app/ui/pages.py`) can refresh whatever depends on
            "is the AI configured" (header button, stale error banner).

    Returns:
        A zero-argument function that opens the dialog.
    """
    provider, console_url = _PROVIDER_LABELS.get(AI_PROVIDER, (AI_PROVIDER, ""))

    with ui.dialog() as dialog, ui.card().classes(
        "w-full max-w-[480px] rounded-card border border-border bg-panel p-6 shadow-card animate-fade-in gap-3"
    ):
        ui.label(t("apiKey.title", provider=provider)).classes("text-[17px] font-bold text-text")
        ui.label(t("apiKey.description")).classes("text-[13px] text-subtext")
        if console_url:
            ui.label(t("apiKey.getKey", url=console_url)).classes("text-[12.5px] text-subtext")

        key_input = (
            ui.input(label=t("apiKey.label"), password=True, password_toggle_button=True)
            # "new-password": browsers ignore autocomplete=off on password
            # fields and may autofill a saved credential for this origin
            # into what has to be an API key.
            .props("outlined dense autocomplete=new-password")
            .classes("w-full")
        )
        status = ui.label().classes("text-[12.5px]")

        def save() -> None:
            if not key_input.value.strip():
                status.set_text(t("apiKey.empty"))
                status.classes(replace="text-[12.5px] text-flag")
                return
            try:
                set_runtime_api_key(key_input.value)
            except InvalidApiKeyError as exc:
                status.set_text(t("apiKey.invalid", char=exc.char, position=exc.position))
                status.classes(replace="text-[12.5px] text-flag")
                return
            dialog.close()
            on_changed()

        def clear() -> None:
            set_runtime_api_key(None)
            dialog.close()
            on_changed()

        key_input.on("keydown.enter", save)

        with ui.row().classes("w-full items-center justify-end gap-2"):
            ui.button(t("apiKey.clear"), on_click=clear).props("flat no-caps").classes("mr-auto text-[13px] text-subtext")
            ui.button(t("apiKey.cancel"), on_click=dialog.close).props("flat no-caps").classes(
                "rounded-control border border-border px-3.5 py-2 text-[13px] text-subtext"
            )
            ui.button(t("apiKey.save"), on_click=save).props("no-caps unelevated").classes(
                "rounded-control bg-accent px-3.5 py-2 text-[13px] font-semibold text-accent-text"
            )

    def open_() -> None:
        key_input.set_value("")
        if is_configured():
            status.set_text(t("apiKey.configured"))
            status.classes(replace="text-[12.5px] text-subtext")
        else:
            status.set_text("")
        dialog.open()

    return open_

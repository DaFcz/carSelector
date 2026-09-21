"""Two-step login dialog: enter an email, then the 6-digit code that was
sent to it. A dialog (not a separate page) on purpose - logging in
mid-conversation must not throw away the chat/results already on screen.
"""

from collections.abc import Callable
from dataclasses import dataclass

from nicegui import ui

from app.core.config import LOGIN_CODE_TTL_MINUTES
from app.ui.auth import AuthState
from app.ui.i18n import STRINGS, t


@dataclass
class _LoginForm:
    """Everything the dialog remembers between renders. `step` is
    `"email"` or `"code"`.
    """

    step: str = "email"
    email: str = ""
    code: str = ""
    error: str | None = None
    busy: bool = False


def login_dialog(auth: AuthState, on_logged_in: Callable[[], None]) -> Callable[[], None]:
    """Builds the (initially closed) login dialog.

    Args:
        auth: This connection's login state; the dialog drives its
            `request_code`/`verify_code`.
        on_logged_in: Called after a successful login, once the dialog has
            closed, so the caller (see `app/ui/pages.py`) can refresh
            whatever depends on who is logged in.

    Returns:
        A zero-argument function that opens the dialog, starting over at
        the email step.
    """
    form = _LoginForm()

    # Handlers come first because `body()` below renders buttons wired to them
    # immediately; they reference `body`/`dialog` only when actually invoked, by
    # which time both exist (same ordering rule as `pages.index`).
    async def submit_email() -> None:
        if form.busy:
            return
        form.busy = True
        form.error = None
        body.refresh()
        error = await auth.request_code(form.email)
        form.busy = False
        if error is None:
            form.step = "code"
            form.code = ""
        else:
            form.error = error
        body.refresh()

    async def resend() -> None:
        if form.busy:
            return
        form.busy = True
        form.error = None
        body.refresh()
        form.error = await auth.request_code(form.email)
        form.busy = False
        body.refresh()

    async def submit_code() -> None:
        if form.busy:
            return
        form.busy = True
        form.error = None
        body.refresh()
        error = await auth.verify_code(form.email, form.code)
        form.busy = False
        if error is None:
            dialog.close()
            on_logged_in()
            return
        form.error = error
        # A burned code can't be retried - send them back to ask for a new one.
        if error == "too_many_attempts":
            form.code = ""
        body.refresh()

    def change_email() -> None:
        form.step = "email"
        form.error = None
        body.refresh()

    with ui.dialog() as dialog, ui.card().classes(
        "w-full max-w-[420px] rounded-card border border-border bg-panel p-6 shadow-card animate-fade-in gap-3"
    ):

        @ui.refreshable
        def body() -> None:
            ui.label(t("auth.title")).classes("text-[17px] font-bold text-text")

            if form.step == "email":
                ui.label(t("auth.emailDescription")).classes("text-[13px] text-subtext")
                email_input = (
                    ui.input(label=t("auth.emailLabel"), value=form.email, on_change=lambda e: setattr(form, "email", e.value))
                    .props("outlined dense type=email autocomplete=email autofocus")
                    .classes("w-full")
                )
                email_input.on("keydown.enter", submit_email)
            else:
                ui.label(t("auth.codeDescription", email=form.email.strip().lower(), minutes=LOGIN_CODE_TTL_MINUTES)).classes(
                    "text-[13px] text-subtext"
                )
                code_input = (
                    ui.input(label=t("auth.codeLabel"), value=form.code, on_change=lambda e: setattr(form, "code", e.value))
                    # one-time-code lets phones offer the code from the
                    # email/SMS notification; numeric brings up the digit pad.
                    .props("outlined dense maxlength=6 inputmode=numeric autocomplete=one-time-code autofocus")
                    .classes("w-full")
                )
                code_input.on("keydown.enter", submit_code)

            if form.error is not None:
                message = STRINGS["auth"]["errors"].get(form.error, STRINGS["auth"]["errors"]["unknown_error"])
                ui.label(message).classes("text-[12.5px] text-flag")

            with ui.row().classes("w-full items-center justify-end gap-2"):
                if form.step == "code":
                    ui.button(t("auth.changeEmail"), on_click=change_email).props("flat no-caps").classes(
                        "mr-auto text-[13px] text-subtext"
                    )
                    ui.button(t("auth.resend"), on_click=resend).props("flat no-caps").classes("text-[13px] text-subtext")
                else:
                    ui.button(t("auth.cancel"), on_click=dialog.close).props("flat no-caps").classes(
                        "rounded-control border border-border px-3.5 py-2 text-[13px] text-subtext"
                    )
                primary = ui.button(
                    (t("auth.sending") if form.busy else t("auth.sendCode"))
                    if form.step == "email"
                    else (t("auth.verifying") if form.busy else t("auth.verify")),
                    on_click=submit_email if form.step == "email" else submit_code,
                ).props("no-caps unelevated").classes(
                    "rounded-control bg-accent px-3.5 py-2 text-[13px] font-semibold text-accent-text"
                )
                primary.set_enabled(not form.busy)

        body()

    def open_() -> None:
        form.step = "email"
        form.code = ""
        form.error = None
        form.busy = False
        body.refresh()
        dialog.open()

    return open_

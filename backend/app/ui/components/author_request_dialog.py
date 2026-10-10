"""The "Stát se autorem" dialog: a logged-in user asks an admin for the
author role (see `app/services/authors.py`). On opening it loads the
user's latest request, so a pending one is shown instead of the form.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from nicegui import ui

from app.schemas.article import AuthorRequestRead
from app.ui import articles_state
from app.ui.auth import AuthState
from app.ui.i18n import STRINGS, t


def error_text(namespace: str, code: str, detail: str = "") -> str:
    """Args:
        namespace: `"authors"` or `"articles"`.
        code: An `Outcome.error`.
        detail: Its `Outcome.detail`.

    Returns:
        The user-facing text for the error (generic if the code is unknown).
    """
    known = STRINGS[namespace]["errors"]
    return t(f"{namespace}.errors.{code if code in known else 'unknown_error'}", detail=detail)


@dataclass
class _RequestForm:
    display_name: str = ""
    message: str = ""
    latest: AuthorRequestRead | None = None
    sent: bool = False
    error: str | None = None
    busy: bool = False


def author_request_dialog(auth: AuthState) -> Callable[[], Awaitable[None]]:
    """Builds the (initially closed) dialog.

    Args:
        auth: This connection's login state - the request is filed for
            `auth.user`. The header only offers the dialog to logged-in
            non-authors, and the service refuses anyone else regardless.

    Returns:
        An async function that opens the dialog.
    """
    form = _RequestForm()

    async def submit() -> None:
        if form.busy or auth.user is None:
            return
        form.busy = True
        form.error = None
        body.refresh()
        outcome = await articles_state.request_author_role(auth.user.id, form.display_name, form.message)
        form.busy = False
        if outcome.ok:
            form.latest = outcome.value
            form.sent = True
        else:
            form.error = error_text("authors", outcome.error)
        body.refresh()

    with (
        ui.dialog() as dialog,
        ui.card().classes(
            "w-full max-w-[460px] rounded-card border border-border bg-panel p-4 md:p-6 shadow-card animate-fade-in gap-3"
        ),
    ):

        @ui.refreshable
        def body() -> None:
            ui.label(t("authors.request.title")).classes("text-[17px] font-bold text-text")
            latest = form.latest
            date_format = t("common.dateFormat")
            if form.sent:
                ui.label(t("authors.request.sent")).classes("text-[13px] text-text").mark("author-request-sent")
            elif latest is not None and latest.status == "pending":
                ui.label(t("authors.request.pending", date=latest.created_at.strftime(date_format))).classes(
                    "text-[13px] text-text"
                ).mark("author-request-pending")
            else:
                ui.label(t("authors.request.description")).classes("text-[13px] text-subtext")
                if latest is not None and latest.status == "rejected":
                    ui.label(t("authors.request.rejected", date=latest.created_at.strftime(date_format))).classes(
                        "w-full rounded-control bg-flag-bg px-3 py-2 text-[12px] text-flag"
                    )
                ui.input(
                    label=t("authors.request.nameLabel"),
                    value=form.display_name,
                    on_change=lambda e: setattr(form, "display_name", e.value),
                ).props("outlined dense maxlength=120 autofocus").classes("w-full").mark("author-name")
                ui.textarea(
                    label=t("authors.request.messageLabel"),
                    value=form.message,
                    on_change=lambda e: setattr(form, "message", e.value),
                ).props("outlined dense maxlength=2000 autogrow").classes("w-full").mark("author-message")
            if form.error:
                ui.label(form.error).classes("text-[12.5px] text-flag")

            with ui.row().classes("w-full items-center justify-end gap-2"):
                ui.button(t("authors.request.close"), on_click=dialog.close).props("flat no-caps").classes(
                    "rounded-control border border-border px-3.5 py-2 text-[13px] text-subtext"
                )
                if not form.sent and not (latest is not None and latest.status == "pending"):
                    button = (
                        ui.button(
                            t("authors.request.sending") if form.busy else t("authors.request.submit"), on_click=submit
                        )
                        .props("no-caps unelevated")
                        .classes("rounded-control bg-accent px-3.5 py-2 text-[13px] font-semibold text-accent-text")
                        .mark("author-request-submit")
                    )
                    button.set_enabled(not form.busy)

        body()

    async def open_() -> None:
        form.sent = False
        form.error = None
        form.busy = False
        form.latest = None
        if auth.user is not None:
            outcome = await articles_state.latest_author_request(auth.user.id)
            form.latest = outcome.value if outcome.ok else None
            if form.latest is not None and not form.display_name:
                form.display_name = form.latest.display_name
        body.refresh()
        dialog.open()

    return open_

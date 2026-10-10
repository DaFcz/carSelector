"""The "Napsat zpětnou vazbu" dialog: a logged-in user sends a bug report,
an idea, praise or anything else to the admins (see
`app/services/feedback.py`). The dialog lists the context sent along with
the text, so nothing is collected without the user seeing it.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from nicegui import ui

from app.core.version import app_version
from app.schemas.feedback import FEEDBACK_TYPES, FeedbackContext
from app.schemas.requirement import StructuredRequirements
from app.ui import feedback_state
from app.ui.auth import AuthState
from app.ui.components.author_request_dialog import error_text
from app.ui.i18n import t

MAX_TEXT_LENGTH = 4000


@dataclass
class _FeedbackForm:
    type: str | None = None
    text: str = ""
    attach_requirements: bool = False
    sent: bool = False
    error: str | None = None
    busy: bool = False


def feedback_dialog(
    auth: AuthState, page: str, get_requirements: Callable[[], StructuredRequirements | None]
) -> Callable[[], Awaitable[None]]:
    """Builds the (initially closed) dialog.

    Args:
        auth: This connection's login state - the feedback is sent as
            `auth.user`. The header only offers the dialog to logged-in
            users, and the service refuses anyone else regardless.
        page: Which part of the app the dialog belongs to (a key under
            `feedback.pages`), stored with the feedback.
        get_requirements: Returns the user's current requirements, or
            `None` if there are none - offered as an opt-in attachment.

    Returns:
        An async function that opens the dialog.
    """
    form = _FeedbackForm()

    async def submit() -> None:
        if form.busy or auth.user is None:
            return
        form.busy = True
        form.error = None
        body.refresh()
        requirements = get_requirements() if form.attach_requirements else None
        context = FeedbackContext(page=page, app_version=app_version(), requirements=requirements)
        outcome = await feedback_state.submit(auth.user.id, form.type or "", form.text, context)
        form.busy = False
        if outcome.ok:
            form.sent = True
        else:
            form.error = error_text("feedback", outcome.error)
        body.refresh()

    with (
        ui.dialog() as dialog,
        ui.card().classes(
            "w-full max-w-[520px] rounded-card border border-border bg-panel p-4 md:p-6 shadow-card animate-fade-in gap-3"
        ),
    ):

        @ui.refreshable
        def body() -> None:
            ui.label(t("feedback.dialog.title")).classes("text-[17px] font-bold text-text")
            if form.sent:
                ui.label(t("feedback.dialog.sent")).classes("text-[13px] text-text").mark("feedback-sent")
            else:
                ui.label(t("feedback.dialog.description")).classes("text-[13px] text-subtext")
                ui.radio(
                    {value: t(f"feedback.types.{value}") for value in FEEDBACK_TYPES},
                    value=form.type,
                    on_change=lambda e: setattr(form, "type", e.value),
                ).props("inline dense").classes("text-[13.5px] text-text").mark("feedback-type")
                ui.textarea(
                    label=t("feedback.dialog.textLabel"),
                    placeholder=t("feedback.dialog.textPlaceholder"),
                    value=form.text,
                    on_change=lambda e: setattr(form, "text", e.value),
                ).props(f"outlined dense maxlength={MAX_TEXT_LENGTH} autogrow counter").classes("w-full").mark(
                    "feedback-text"
                )
                if get_requirements() is not None:
                    ui.checkbox(
                        t("feedback.dialog.attachRequirements"),
                        value=form.attach_requirements,
                        on_change=lambda e: setattr(form, "attach_requirements", e.value),
                    ).classes("text-[13px] text-text").mark("feedback-attach-requirements")
                version = app_version() or "—"
                ui.label(t("feedback.dialog.contextNote", version=version, page=t(f"feedback.pages.{page}"))).classes(
                    "text-[11.5px] text-subtext"
                )
            if form.error:
                ui.label(form.error).classes("text-[12.5px] text-flag").mark("feedback-error")

            with ui.row().classes("w-full items-center justify-end gap-2"):
                ui.button(t("feedback.dialog.close"), on_click=dialog.close).props("flat no-caps").classes(
                    "rounded-control border border-border px-3.5 py-2 text-[13px] text-subtext"
                )
                if not form.sent:
                    button = (
                        ui.button(
                            t("feedback.dialog.sending") if form.busy else t("feedback.dialog.submit"), on_click=submit
                        )
                        .props("no-caps unelevated")
                        .classes("rounded-control bg-accent px-3.5 py-2 text-[13px] font-semibold text-accent-text")
                        .mark("feedback-submit")
                    )
                    button.set_enabled(not form.busy)

        body()

    async def open_() -> None:
        # A fresh form each time - but a half-written, unsent text survives
        # closing the dialog by accident.
        if form.sent:
            form.type = None
            form.text = ""
            form.attach_requirements = False
        form.sent = False
        form.error = None
        form.busy = False
        body.refresh()
        dialog.open()

    return open_

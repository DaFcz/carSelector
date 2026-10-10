"""The admin console's "Zpětná vazba" tab: feedback from users, newest
first, filterable by type and status. Each item can be given a status and
an internal note - see `app/services/feedback.py`.

Admin-only by construction: built solely from `app/ui/admin.py`'s page,
after its `is_admin` check; the service re-checks every action anyway.
"""

from dataclasses import dataclass

from nicegui import ui

from app.schemas.feedback import FEEDBACK_STATUSES, FEEDBACK_TYPES, FeedbackRead
from app.ui import feedback_state
from app.ui.components.author_request_dialog import error_text
from app.ui.i18n import t

_ROW = "w-full rounded-control border border-border bg-panel px-3.5 py-2.5"
_FILTER = "min-w-[160px] rounded-control border border-border bg-panel-2 px-2.5 py-1 text-[13px] text-text"
# Status badge colors: unhandled items stand out, closed ones fade.
_STATUS_CLASSES = {
    "new": "bg-accent text-accent-text",
    "in_progress": "bg-accent-soft text-accent",
    "resolved": "bg-panel-2 text-subtext",
    "wont_fix": "bg-panel-2 text-subtext",
    "duplicate": "bg-panel-2 text-subtext",
}


@dataclass
class _Filters:
    type: str | None = None
    status: str | None = None


async def feedback_admin_panel(admin_id: int) -> None:
    """Builds the tab.

    Args:
        admin_id: The logged-in admin, passed to every service call.
    """
    filters = _Filters()

    async def save(item: FeedbackRead, status: str, note: str) -> None:
        outcome = await feedback_state.update(admin_id, item.id, status, note)
        if outcome.ok:
            ui.notify(t("feedback.admin.saved"))
        else:
            ui.notify(error_text("feedback", outcome.error), type="negative")
        await content.refresh()

    async def set_filter(field: str, value: str | None) -> None:
        setattr(filters, field, value or None)
        await content.refresh()

    def item_row(item: FeedbackRead) -> None:
        date = item.created_at.strftime(t("common.dateFormat") + " %H:%M")
        with ui.column().classes(_ROW + " gap-1.5").mark("feedback-row"):
            with ui.row().classes("w-full flex-nowrap items-center gap-2"):
                ui.label(t(f"feedback.statuses.{item.status}")).classes(
                    f"shrink-0 rounded-full px-2 py-0.5 text-[11px] font-bold {_STATUS_CLASSES[item.status]}"
                )
                ui.label(t(f"feedback.types.{item.type}")).classes("shrink-0 text-[12.5px] font-semibold text-text")
                ui.label(f"{item.email} · {date}").classes("min-w-0 flex-1 text-[11.5px] text-subtext break-all")
            ui.label(item.text).classes("whitespace-pre-wrap text-[13px] text-text")
            ui.label(_context_line(item)).classes("text-[11.5px] text-subtext")
            if item.context.requirements is not None:
                with ui.expansion(t("feedback.admin.requirements")).props("dense").classes("w-full text-[12px]"):
                    ui.code(item.context.requirements.model_dump_json(indent=2, exclude_defaults=True), language="json")
            with ui.row().classes("w-full items-start gap-2"):
                status = (
                    ui.select(
                        {value: t(f"feedback.statuses.{value}") for value in FEEDBACK_STATUSES}, value=item.status
                    )
                    .props("outlined dense options-dense")
                    .classes("min-w-[160px] text-[13px]")
                    .mark("feedback-status")
                )
                note = (
                    ui.textarea(label=t("feedback.admin.note"), value=item.admin_note)
                    .props("outlined dense autogrow maxlength=4000")
                    .classes("min-w-0 flex-1 text-[13px]")
                    .mark("feedback-note")
                )
                ui.button(
                    t("feedback.admin.save"), on_click=lambda i=item, s=status, n=note: save(i, s.value, n.value)
                ).props("no-caps unelevated").classes(
                    "shrink-0 rounded-control bg-accent px-3.5 py-2 text-[13px] font-semibold text-accent-text"
                ).mark("feedback-save")

    @ui.refreshable
    async def content() -> None:
        outcome = await feedback_state.list_for_admin(admin_id, filters.type, filters.status)
        if not outcome.ok:
            ui.label(error_text("feedback", outcome.error)).classes("text-[13px] text-flag")
        elif not outcome.value:
            ui.label(t("feedback.admin.empty")).classes("text-[13px] text-subtext")
        else:
            for item in outcome.value:
                item_row(item)

    with ui.column().classes("w-full max-w-[860px] gap-3"):
        with ui.row().classes("w-full items-center gap-2"):
            ui.select(
                {"": t("feedback.admin.allTypes")} | {value: t(f"feedback.types.{value}") for value in FEEDBACK_TYPES},
                value="",
                on_change=lambda e: set_filter("type", e.value),
            ).props("borderless dense options-dense").classes(_FILTER).mark("feedback-filter-type")
            ui.select(
                {"": t("feedback.admin.allStatuses")}
                | {value: t(f"feedback.statuses.{value}") for value in FEEDBACK_STATUSES},
                value="",
                on_change=lambda e: set_filter("status", e.value),
            ).props("borderless dense options-dense").classes(_FILTER).mark("feedback-filter-status")
        with ui.column().classes("w-full gap-2"):
            await content()


def _context_line(item: FeedbackRead) -> str:
    """Args:
        item: The feedback item.

    Returns:
        One line with the captured context: where, which version, which
        UI language.
    """
    page = t(f"feedback.pages.{item.context.page}") if item.context.page else "—"
    return t(
        "feedback.admin.context", page=page, version=item.context.app_version or "—", language=item.language.upper()
    )

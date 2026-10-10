"""The admin console's "Autoři" tab: pending author-role requests to
approve or reject, and the current authors (with a way to take the role
away again) - see `app/services/authors.py`.

Admin-only by construction: built solely from `app/ui/admin.py`'s page,
after its `is_admin` check; the service re-checks every action anyway.
"""

from nicegui import ui

from app.schemas.article import AuthorRead, AuthorRequestRead
from app.ui import articles_state
from app.ui.components.author_request_dialog import error_text
from app.ui.i18n import t

_SECTION_TITLE = "text-[13px] font-bold uppercase tracking-wide text-subtext"
_ROW = "w-full flex-nowrap items-center gap-3 rounded-control border border-border bg-panel px-3.5 py-2.5"


async def authors_admin_panel(admin_id: int) -> None:
    """Builds the tab.

    Args:
        admin_id: The logged-in admin, passed to every service call.
    """

    async def act(outcome_coro, success: str) -> None:
        outcome = await outcome_coro
        if outcome.ok:
            ui.notify(success)
        else:
            ui.notify(error_text("authors", outcome.error), type="negative")
        await content.refresh()

    def request_row(request: AuthorRequestRead) -> None:
        with ui.row().classes(_ROW).mark("author-request-row"):
            with ui.column().classes("min-w-0 flex-1 gap-0"):
                ui.label(f"{request.display_name} · {request.email}").classes(
                    "text-[13px] font-semibold text-text break-all"
                )
                ui.label(
                    t("authors.admin.requested", date=request.created_at.strftime(t("common.dateFormat")))
                ).classes("text-[11.5px] text-subtext")
                if request.message:
                    ui.label(request.message).classes("mt-1 whitespace-pre-wrap text-[12.5px] text-text")
            ui.button(
                t("authors.admin.reject"),
                on_click=lambda r=request: act(
                    articles_state.decide_request(admin_id, r.id, approve=False),
                    t("authors.admin.rejectedNote", email=r.email),
                ),
            ).props("flat no-caps").classes("shrink-0 text-[13px] text-flag").mark("reject-author")
            ui.button(
                t("authors.admin.approve"),
                on_click=lambda r=request: act(
                    articles_state.decide_request(admin_id, r.id, approve=True),
                    t("authors.admin.approved", email=r.email),
                ),
            ).props("no-caps unelevated").classes(
                "shrink-0 rounded-control bg-accent px-3.5 py-2 text-[13px] font-semibold text-accent-text"
            ).mark("approve-author")

    def author_row(author: AuthorRead) -> None:
        with ui.row().classes(_ROW).mark("author-row"):
            with ui.column().classes("min-w-0 flex-1 gap-0"):
                ui.label(f"{author.display_name or '—'} · {author.email}").classes(
                    "text-[13px] font-semibold text-text break-all"
                )
                ui.label(t("authors.admin.articleCount", count=author.article_count)).classes(
                    "text-[11.5px] text-subtext"
                )
            ui.button(
                t("authors.admin.revoke"),
                on_click=lambda a=author: act(
                    articles_state.revoke_author(admin_id, a.user_id), t("authors.admin.revoked", email=a.email)
                ),
            ).props("flat no-caps").classes("shrink-0 text-[13px] text-flag").mark("revoke-author")

    @ui.refreshable
    async def content() -> None:
        pending = await articles_state.list_pending_requests(admin_id)
        current = await articles_state.list_authors(admin_id)
        with ui.column().classes("w-full max-w-[720px] gap-6"):
            with ui.column().classes("w-full gap-2"):
                ui.label(t("authors.admin.pendingTitle")).classes(_SECTION_TITLE)
                if not pending.ok:
                    ui.label(error_text("authors", pending.error)).classes("text-[13px] text-flag")
                elif not pending.value:
                    ui.label(t("authors.admin.noPending")).classes("text-[13px] text-subtext")
                else:
                    for request in pending.value:
                        request_row(request)
            with ui.column().classes("w-full gap-2"):
                ui.label(t("authors.admin.authorsTitle")).classes(_SECTION_TITLE)
                if not current.ok:
                    ui.label(error_text("authors", current.error)).classes("text-[13px] text-flag")
                elif not current.value:
                    ui.label(t("authors.admin.noAuthors")).classes("text-[13px] text-subtext")
                else:
                    for author in current.value:
                        author_row(author)

    await content()

"""The public, read-only page behind a shared link, `/s/<token>` (see
`app/services/sharing.py`). No login and no app state: it only renders the
frozen snapshot - requirements and cars with prices as of the day it was
shared - plus a way to pass it on (the same share dialog) and a link into
the app to start one's own search.

Registered from `app/main.py`, like `app/ui/admin.py`'s page.
"""

from nicegui import ui

from app.ui.components.results_grid import car_card
from app.ui.components.share_dialog import share_dialog
from app.ui.i18n import t, t_count
from app.ui.pages import MOBILE_VIEWPORT
from app.ui.state import fetch_shared_snapshot
from app.ui.styles import register_styles

# Shared links are private-by-obscurity: keep them out of search engines.
_NOINDEX = '<meta name="robots" content="noindex, nofollow">'


def register_shared_page() -> None:
    """Registers `@ui.page("/s/{token}")` as a side effect - called once
    from `app/main.py`."""

    @ui.page("/s/{token}", viewport=MOBILE_VIEWPORT, title=t("share.pageTitle"))
    async def shared(token: str) -> None:
        register_styles()
        ui.add_head_html(_NOINDEX)
        snapshot = await fetch_shared_snapshot(token)

        with ui.column().classes("min-h-[100dvh] w-full bg-bg text-text gap-0"):
            with ui.row().classes(
                "w-full items-center justify-between gap-3 border-b border-border bg-panel px-4 py-3 md:px-7"
            ):
                ui.link(t("header.brand"), "/").classes("text-[17px] font-bold text-text no-underline")
                ui.link(t("share.findOwn"), "/").classes(
                    "rounded-control bg-accent px-3.5 py-2 text-[13px] font-semibold text-accent-text no-underline"
                )

            with ui.column().classes("w-full max-w-[1000px] self-center gap-0 px-4 py-5 md:px-7 md:py-7"):
                if snapshot is None:
                    ui.label(t("share.notFound")).classes("text-[17px] font-bold text-text")
                    ui.label(t("share.notFoundHint")).classes("mt-1 text-[13px] text-subtext")
                    return

                content = snapshot.content
                open_share = share_dialog()
                with ui.row().classes("w-full flex-wrap items-start justify-between gap-3"):
                    with ui.column().classes("gap-0"):
                        ui.label(t_count("share.heading", len(content.vehicles))).classes(
                            "text-[19px] font-bold text-text"
                        )
                        ui.label(
                            t(
                                "share.asOf",
                                created=snapshot.created_at.strftime(t("common.dateFormat")),
                                expires=snapshot.expires_at.strftime(t("common.dateFormat")),
                            )
                        ).classes("mt-0.5 text-[13px] text-subtext")
                    ui.button(t("share.button"), icon="share", on_click=lambda: open_share(snapshot)).props(
                        "flat no-caps"
                    ).classes(
                        "rounded-control border border-border bg-panel-2 px-3 py-1.5 text-[13px] font-semibold text-text"
                    ).mark("reshare")

                if content.requirements:
                    with ui.column().classes("mt-5 w-full gap-2"):
                        ui.label(t("share.requirements")).classes(
                            "text-[13px] font-bold uppercase tracking-wide text-subtext"
                        )
                        with ui.row().classes("w-full flex-wrap gap-2"):
                            for req in content.requirements:
                                with ui.column().classes(
                                    "gap-0 rounded-control border border-border bg-panel px-3 py-2"
                                ):
                                    ui.label(req.label).classes(
                                        "text-[10.5px] font-bold uppercase tracking-wide text-subtext"
                                    )
                                    ui.label(req.value).classes("text-[13.5px] font-semibold text-text")

                with ui.row().classes("mt-6 w-full gap-4"):
                    for car in content.vehicles:
                        with ui.column().classes("w-full sm:w-[230px] gap-0"):
                            car_card(car, on_select=None)

                ui.label(t("share.priceNote")).classes("mt-6 text-[12px] text-subtext")

"""The "share" dialog: shows a shared result's link with three ways to pass
it on - copy it, hand it to the phone's own share sheet (Web Share API:
WhatsApp, Messenger, SMS, ...), or show its QR code (e.g. at a dealership).

Built once per page, like `vehicle_detail_modal`; the returned `open_for`
is called with a snapshot that's already been stored (see
`app/ui/state.py`'s `create_shared_snapshot`).
"""

import json
from collections.abc import Callable

import segno
from nicegui import ui

from app.core import config
from app.schemas.sharing import SharedSnapshot
from app.ui.i18n import t

# Hidden until the browser says it supports `navigator.share` (see `_reveal_native_share`).
_NATIVE_SHARE_CLASS = "native-share"


def shared_url(token: str) -> str:
    """Args:
        token: A shared snapshot's token.

    Returns:
        The absolute link to it - on `PUBLIC_BASE_URL` if set, else on the
        origin the current page was requested from.
    """
    base = config.PUBLIC_BASE_URL or str(ui.context.client.request.base_url).rstrip("/")
    return f"{base}/s/{token}"


def qr_svg(url: str) -> str:
    """Args:
        url: What the code should open.

    Returns:
        An inline `<svg>` QR code, black on white in both color themes (a
        code on a dark background scans badly).
    """
    return segno.make(url, error="m").svg_inline(scale=5, border=2, dark="#000", light="#fff")


def share_dialog() -> Callable[[SharedSnapshot], None]:
    """Builds the (initially closed) share dialog.

    Returns:
        A function to call with a stored snapshot to show its link.
    """
    state: dict[str, SharedSnapshot | None] = {"snapshot": None}

    with (
        ui.dialog().classes("dialog-mobile-full") as dialog,
        ui.card().classes("w-full max-w-[440px] rounded-card border border-border bg-panel p-4 md:p-6 shadow-card"),
    ):

        @ui.refreshable
        def _content() -> None:
            snapshot = state["snapshot"]
            if snapshot is None:
                return
            url = shared_url(snapshot.token)
            expires = snapshot.expires_at.strftime(t("common.dateFormat"))

            with ui.row().classes("w-full flex-nowrap items-start justify-between gap-3"):
                ui.label(t("share.title")).classes("text-[17px] font-bold text-text")
                ui.button(t("share.close"), on_click=dialog.close).props("flat no-caps").classes(
                    "shrink-0 rounded-control border border-border bg-panel-2 px-3 py-1.5 text-[13px] font-semibold text-text"
                )
            ui.label(t("share.description", date=expires)).classes("mt-1 text-[12.5px] text-subtext")

            ui.input(value=url).props("readonly outlined dense").classes("mt-4 w-full").mark("share-url")

            with ui.row().classes("mt-3 w-full flex-wrap gap-2"):

                def _copy() -> None:
                    ui.clipboard.write(url)
                    ui.notify(t("share.copied"), type="positive")

                ui.button(t("share.copy"), icon="content_copy", on_click=_copy).props("unelevated no-caps").classes(
                    "rounded-control bg-accent px-3.5 py-2 text-[13px] font-semibold text-accent-text"
                )
                # Handled entirely in the browser: `navigator.share` must run
                # inside the click itself (a round trip to the server first
                # can lose the "user gesture" some browsers require).
                payload = json.dumps({"title": t("share.nativeTitle"), "url": url})
                ui.button(t("share.native"), icon="ios_share").props("flat no-caps").classes(
                    f"{_NATIVE_SHARE_CLASS} hidden rounded-control border border-border bg-panel-2 px-3.5 py-2 "
                    "text-[13px] font-semibold text-text"
                ).on("click", js_handler=f"() => navigator.share({payload}).catch(() => {{}})")

            with ui.column().classes("mt-4 w-full items-center gap-1"):
                ui.html(qr_svg(url)).classes("rounded-control border border-border bg-white p-1").mark("share-qr")
                ui.label(t("share.qrHint")).classes("text-[12px] text-subtext")

        _content()

    def open_for(snapshot: SharedSnapshot) -> None:
        """Shows the dialog for `snapshot`.

        Args:
            snapshot: An already-stored snapshot.
        """
        state["snapshot"] = snapshot
        _content.refresh()
        dialog.open()
        ui.run_javascript(
            f"if (navigator.share) document.querySelectorAll('.{_NATIVE_SHARE_CLASS}')"
            ".forEach((el) => el.classList.remove('hidden'))"
        )

    return open_for

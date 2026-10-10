"""Port of frontend/src/components/AppHeader.tsx."""

from collections.abc import Callable
from typing import Any

from nicegui import ui

from app.schemas.auth import UserRead
from app.ui.i18n import t

_ICON_BUTTON_CLASSES = "shrink-0 rounded-control border border-border text-subtext w-9 h-9 min-h-0"


def app_header(
    requirements_count: int,
    on_restart: Callable[[], None],
    on_toggle_drawer: Callable[[], None],
    on_open_wizard: Callable[[], None],
    ai_configured: bool,
    on_open_api_key: Callable[[], None],
    user: UserRead | None,
    on_login: Callable[[], None],
    on_logout: Callable[[], None],
    on_switch_language: Callable[[], None],
    on_request_author: Callable[[], Any],
    on_send_feedback: Callable[[], Any],
) -> None:
    """Builds the top bar: brand/tagline on the left; on the right the two
    car-finding actions (wizard, requirements drawer), a restart icon, and
    an account button whose menu holds everything about the user and the
    app - email, articles, admin link, API key, language, login/logout. The same
    layout serves desktop and mobile (the tagline and the requirements
    label just collapse below `md`), so there's no separate mobile menu.

    Args:
        requirements_count: Shown as a badge on the drawer-toggle button.
        on_restart: Called when the restart icon is clicked.
        on_toggle_drawer: Called when the requirements button is clicked.
        on_open_wizard: Called when "Průvodce výběrem" is clicked - opens
            the guided question-by-question alternative to the free-text
            chat (see `app/ui/components/wizard.py`).
        ai_configured: Whether an AI API key is set - for admins, a missing
            key flags the account button and its menu item.
        on_open_api_key: Called when the API-key menu item is clicked -
            opens `app/ui/components/api_key_dialog.py`. Only ever shown to
            admins, since the key is process-wide.
        user: The logged-in user, or `None` if anonymous. Decides
            whether admin-only controls are shown - cosmetic only, the
            server-side checks live where the privileged actions do (see
            `app/ui/auth.py`).
        on_login: Called when "Přihlásit se" is clicked - opens
            `app/ui/components/login_dialog.py`.
        on_logout: Called when "Odhlásit" is clicked.
        on_switch_language: Called when the language menu item is clicked.
        on_request_author: Called when "Stát se autorem" is clicked - opens
            `app/ui/components/author_request_dialog.py`. Offered only to
            logged-in users who can't write articles yet.
        on_send_feedback: Called when "Napsat zpětnou vazbu" is clicked -
            opens `app/ui/components/feedback_dialog.py`. Offered only to
            logged-in users.
    """
    is_admin = user is not None and user.is_admin
    key_missing = is_admin and not ai_configured
    with ui.row().classes(
        "relative shrink-0 flex-nowrap items-center justify-between gap-3 border-b border-border "
        "px-4 py-3 md:px-7 md:py-4.5 w-full"
    ):
        with ui.column().classes("min-w-0 gap-0.5"):
            ui.label(t("header.brand")).classes("text-xl font-bold tracking-tight text-text")
            ui.label(t("header.tagline")).classes("text-[12.5px] text-subtext max-md:hidden!")

        with ui.row().classes("flex-nowrap items-center gap-2 md:gap-2.5"):
            ui.button(t("header.startWizard"), on_click=on_open_wizard).props("no-caps unelevated").classes(
                "shrink-0 rounded-control bg-accent px-3.5 py-2 text-[13px] font-semibold text-accent-text "
                "whitespace-nowrap max-md:px-3"
            )
            with (
                ui.button(on_click=on_toggle_drawer)
                .props("flat no-caps")
                .classes(
                    "relative shrink-0 flex flex-nowrap items-center gap-2 rounded-control border border-border bg-panel-2 "
                    "px-3.5 py-2 max-md:w-9 max-md:h-9 max-md:min-h-0 max-md:p-0 "
                    "text-[13px] font-semibold text-text"
                )
                .tooltip(t("header.technicalRequirements"))
                .mark("requirements-toggle")
            ):
                ui.label(t("header.technicalRequirements")).classes("max-md:hidden!")
                ui.icon("tune", size="18px").classes("md:hidden!")
                # A corner bubble on the icon-only phone button, inline on desktop.
                ui.label(str(requirements_count)).classes(
                    "rounded-full bg-accent px-[7px] py-0.5 text-[11px] font-bold text-accent-text "
                    "max-md:absolute max-md:-top-2 max-md:-right-2 max-md:px-[5px] max-md:py-0 max-md:leading-4"
                )

            ui.button(icon="refresh", on_click=on_restart).props("flat dense").classes(_ICON_BUTTON_CLASSES).tooltip(
                t("header.restart")
            ).mark("restart")

            _account_menu(
                user,
                is_admin,
                key_missing,
                on_open_api_key,
                on_login,
                on_logout,
                on_switch_language,
                on_request_author,
                on_send_feedback,
            )


def _account_menu(
    user: UserRead | None,
    is_admin: bool,
    key_missing: bool,
    on_open_api_key: Callable[[], None],
    on_login: Callable[[], None],
    on_logout: Callable[[], None],
    on_switch_language: Callable[[], None],
    on_request_author: Callable[[], Any],
    on_send_feedback: Callable[[], Any],
) -> None:
    """The round account button and its dropdown - see `app_header`.

    Args:
        user: The logged-in user, or `None` if anonymous - an initial
            avatar when logged in, a person icon otherwise.
        is_admin: Whether to list the admin link and API-key item.
        key_missing: Flags the button (a dot) and the API-key item, so a
            missing key isn't hidden away inside the menu.
        on_open_api_key: See `app_header`.
        on_login: See `app_header`.
        on_logout: See `app_header`.
        on_switch_language: See `app_header`.
        on_request_author: See `app_header`.
        on_send_feedback: See `app_header`.
    """
    avatar_classes = "relative shrink-0 rounded-full w-9 h-9 min-h-0 "
    if user is not None:
        button = (
            ui.button(user.email[:1].upper())
            .props("flat dense no-caps")
            .classes(avatar_classes + "bg-accent-soft text-accent text-[14px] font-bold")
        )
    else:
        button = (
            ui.button(icon="person").props("flat dense").classes(avatar_classes + "border border-border text-subtext")
        )
    button.tooltip(t("header.account")).mark("account-menu")

    with button:
        if key_missing:
            ui.element("span").classes("absolute top-0 right-0 w-2.5 h-2.5 rounded-full bg-flag border-2 border-panel")
        with (
            ui.menu()
            .props("anchor='bottom right' self='top right'")
            .classes("min-w-[220px] rounded-control border border-border bg-panel")
        ):
            if user is not None:
                ui.label(user.email).classes("px-4 pt-2.5 pb-2 text-[12.5px] text-subtext break-all")
                ui.separator()
            _menu_item("article", t("header.articles"), lambda: ui.navigate.to("/articles")).mark("menu-articles")
            if user is not None and user.can_write_articles:
                _menu_item("edit_note", t("header.myArticles"), lambda: ui.navigate.to("/author")).mark(
                    "menu-my-articles"
                )
            elif user is not None:
                _menu_item("history_edu", t("header.becomeAuthor"), on_request_author).mark("menu-become-author")
            if user is not None:
                _menu_item("feedback", t("header.sendFeedback"), on_send_feedback).mark("menu-feedback")
            if is_admin:
                _menu_item("admin_panel_settings", t("header.admin"), lambda: ui.navigate.to("/admin")).mark(
                    "menu-admin"
                )
                _menu_item(
                    "key",
                    t("header.apiKeyMissing") if key_missing else t("header.apiKey"),
                    on_open_api_key,
                    flagged=key_missing,
                ).mark("menu-api-key")
            _menu_item("translate", t("header.switchLanguage"), on_switch_language).mark("language-toggle")
            ui.separator()
            if user is None:
                _menu_item("login", t("header.login"), on_login).mark("login")
            else:
                _menu_item("logout", t("header.logout"), on_logout).mark("logout")


def _menu_item(icon: str, label: str, on_click: Callable[[], Any], *, flagged: bool = False) -> ui.menu_item:
    """One account-menu row: icon + label. Tests click rows by marker -
    NiceGUI's test `User` matches text on the inner label, which (unlike in
    a browser) doesn't pass the click up to the item.

    Args:
        icon: Material icon name.
        label: Row text.
        on_click: Called on click; the menu closes itself.
        flagged: Renders the row in the warning color.

    Returns:
        The menu item.
    """
    color = "text-flag" if flagged else "text-text"
    with ui.menu_item(on_click=on_click).classes(f"items-center gap-3 text-[13px] {color}") as item:
        ui.icon(icon, size="18px")
        ui.label(label)
    return item

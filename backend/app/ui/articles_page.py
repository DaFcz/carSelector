"""The articles portal:

- `/articles`: every article the visitor may read (see
  `app/services/articles.py`) - public ones for everyone, plus those
  shared with the logged-in reader;
- `/articles/{id}`: one article;
- `/author`: an author's own articles, drafts included;
- `/author/new`, `/author/edit/{id}`: the WYSIWYG editor (NiceGUI's
  `ui.editor`, i.e. Quasar's QEditor) - one tab per language, Czech and/or
  English - with the choice of who may read it.

Readers get the language version matching the UI language (switchable in
the top bar); an article missing it is shown in the language it has, with
a notice saying so.

Author pages build nothing but a "no rights" note for users who can't
write (same wall as `app/ui/admin.py`), and every save/delete is checked
again by the service. Article HTML is rendered through `ui.html`'s default
client-side DOMPurify sanitization - an author can't run scripts in a
reader's browser.

Registered from `app/main.py`, like `app/ui/admin.py`'s page.
"""

import re
from collections.abc import Awaitable, Callable

from nicegui import ui

from app.schemas.article import ARTICLE_LANGUAGES, ArticleDraft, ArticleRead, ArticleSummary, ArticleTranslation
from app.ui import articles_state
from app.ui.auth import AuthState
from app.ui.components.author_request_dialog import error_text
from app.ui.components.login_dialog import login_dialog
from app.ui.i18n import LANGUAGES, current_language, set_language, t
from app.ui.pages import MOBILE_VIEWPORT
from app.ui.styles import register_styles

VISIBILITIES = ("draft", "restricted", "public")

# Quasar QEditor toolbar: alignment, inline formatting, block format,
# lists/quote, link/rule, undo/redo, raw-HTML toggle.
_TOOLBAR_GROUPS: list[list] = [
    ["bold", "italic", "underline", "strike"],
    ["h2", "h3", "p"],
    ["unordered", "ordered", "quote", "outdent", "indent"],
    ["left", "center", "right", "justify"],
    ["link", "hr", "removeFormat"],
    ["undo", "redo"],
    ["viewsource"],
]

_BUTTON_PRIMARY = "rounded-control bg-accent px-3.5 py-2 text-[13px] font-semibold text-accent-text"
_BUTTON_SECONDARY = "rounded-control border border-border bg-panel-2 px-3.5 py-2 text-[13px] font-semibold text-text"


def split_recipients(raw: str) -> list[str]:
    """Args:
        raw: The recipients field as typed - addresses separated by commas,
            semicolons, spaces or new lines.

    Returns:
        The non-empty pieces (validated later by the service).
    """
    return [part for part in re.split(r"[\s,;]+", raw) if part]


def _byline(article: ArticleSummary) -> str:
    when = article.published_at or article.updated_at
    return t(
        "articles.byline",
        author=article.author_name or t("articles.editorial"),
        date=when.strftime(t("common.dateFormat")),
    )


def _badge(text: str, *, accent: bool = False) -> None:
    ui.label(text).classes(
        "rounded-full px-2.5 py-0.5 text-[11px] font-semibold "
        + ("bg-accent-soft text-accent" if accent else "bg-panel-2 text-subtext")
    )


def _page_shell(auth_state: AuthState) -> ui.column:
    """The top bar shared by every portal page, plus the content column.

    Args:
        auth_state: This connection's login state - anonymous visitors
            get a login button (the page reloads after logging in, so
            restricted articles appear), writers a link to their articles.

    Returns:
        The content column to build the page into.
    """
    # Captured now, not at reload time - see `app/ui/admin.py`'s
    # `_access_denied` for why.
    client = ui.context.client

    def reload_page() -> None:
        with client:
            ui.navigate.reload()

    open_login = login_dialog(auth_state, reload_page)

    def switch_language() -> None:
        # Same toggle as the main page's (`app/ui/pages.py`) - the reload
        # rebuilds the page and refetches articles in the new language.
        language = current_language()
        set_language(LANGUAGES[(LANGUAGES.index(language) + 1) % len(LANGUAGES)])
        reload_page()

    with ui.column().classes("min-h-[100dvh] w-full bg-bg text-text gap-0"):
        with ui.row().classes(
            "w-full flex-nowrap items-center justify-between gap-3 border-b border-border bg-panel px-4 py-3 md:px-7"
        ):
            with ui.row().classes("items-center gap-4"):
                ui.link(t("header.brand"), "/").classes("text-[17px] font-bold text-text no-underline")
                ui.link(t("header.articles"), "/articles").classes(
                    "text-[13px] font-semibold text-subtext no-underline"
                )
                if auth_state.can_write_articles:
                    ui.link(t("header.myArticles"), "/author").classes(
                        "text-[13px] font-semibold text-subtext no-underline"
                    ).mark("nav-my-articles")
            with ui.row().classes("flex-nowrap items-center gap-2"):
                ui.button(t("header.switchLanguage"), icon="translate", on_click=switch_language).props(
                    "flat dense no-caps"
                ).classes("text-[13px] text-subtext").mark("language-toggle")
                if auth_state.user is None:
                    ui.button(t("header.login"), icon="login", on_click=open_login).props("flat no-caps").classes(
                        _BUTTON_SECONDARY
                    ).mark("login")
                else:
                    ui.label(auth_state.user.email).classes("text-[12.5px] text-subtext max-md:hidden!")
        content = ui.column().classes("w-full max-w-[820px] self-center gap-0 px-4 py-5 md:px-7 md:py-7")
    return content


def _articles_list(auth_state: AuthState, items: list[ArticleSummary]) -> None:
    ui.label(t("articles.title")).classes("text-[22px] font-bold text-text")
    if not items:
        ui.label(t("articles.empty")).classes("mt-3 text-[13px] text-subtext")
        return
    viewer_id = auth_state.user.id if auth_state.user else None
    with ui.column().classes("mt-4 w-full gap-3"):
        for article in items:
            with (
                ui.link(target=f"/articles/{article.id}")
                .classes("w-full no-underline rounded-card border border-border bg-panel px-4 py-3.5 shadow-card")
                .mark("article-link")
            ):
                ui.label(article.title).classes("text-[16px] font-bold text-text")
                with ui.row().classes("mt-1 items-center gap-2"):
                    ui.label(_byline(article)).classes("text-[12.5px] text-subtext")
                    if article.language != current_language():
                        _badge(t(f"articles.onlyInBadge.{article.language}"))
                    if article.visibility == "restricted":
                        # The author sees their own restricted articles here too.
                        own = article.author_id == viewer_id
                        _badge(t("articles.visibility.restricted") if own else t("articles.sharedWithYou"), accent=True)


def _article_view(auth_state: AuthState, article: ArticleRead) -> None:
    is_own = auth_state.user is not None and auth_state.user.id == article.author_id
    ui.link(t("articles.backToList"), "/articles").classes("text-[13px] text-accent")
    ui.label(article.title).classes("mt-3 text-[26px] font-bold leading-tight text-text").mark("article-title")
    with ui.row().classes("mt-1.5 w-full items-center gap-2"):
        ui.label(_byline(article)).classes("text-[13px] text-subtext")
        if is_own:
            _badge(t(f"articles.visibility.{article.visibility}"), accent=article.visibility != "draft")
            ui.link(t("articles.edit"), f"/author/edit/{article.id}").classes("ml-auto text-[13px] text-accent")
        elif article.visibility == "restricted":
            _badge(t("articles.sharedWithYou"), accent=True)
    _language_note(article)
    # sanitize=True (the default): DOMPurify in the reader's browser.
    ui.html(article.content_html).classes("article-body mt-5 w-full text-text").mark("article-body")


def _language_note(article: ArticleRead) -> None:
    """Says the article isn't in the reader's language, or - when it is
    and another version exists too - offers that one."""
    language = current_language()
    if article.language != language:
        with (
            ui.row()
            .classes(
                "mt-4 w-full flex-nowrap items-center gap-2 rounded-control border border-border bg-panel-2 px-3.5 py-2.5"
            )
            .mark("article-language-notice")
        ):
            ui.icon("translate").classes("text-[18px] text-subtext")
            ui.label(t(f"articles.onlyIn.{article.language}")).classes("text-[13px] text-text")
        return
    client = ui.context.client

    def read_in(other: str) -> None:
        set_language(other)
        with client:
            ui.navigate.reload()

    for other in article.languages:
        if other != language:
            ui.button(
                t(f"articles.readIn.{other}"), icon="translate", on_click=lambda other=other: read_in(other)
            ).props("flat dense no-caps").classes("mt-2 text-[13px] text-accent").mark("article-read-in")


def _not_allowed(auth_state: AuthState) -> None:
    ui.label(t("articles.author.onlyAuthors")).classes("text-[17px] font-bold text-text")
    if auth_state.user is not None:
        ui.label(t("articles.author.onlyAuthorsHint")).classes("mt-1 text-[13px] text-subtext")
    ui.link(t("articles.backToApp"), "/").classes("mt-3 text-[13px] text-accent")


def _own_list(items: list[ArticleSummary]) -> None:
    with ui.row().classes("w-full items-center justify-between gap-3"):
        ui.label(t("articles.author.title")).classes("text-[22px] font-bold text-text")
        ui.button(t("articles.author.new"), icon="add", on_click=lambda: ui.navigate.to("/author/new")).props(
            "no-caps unelevated"
        ).classes(_BUTTON_PRIMARY).mark("new-article")
    if not items:
        ui.label(t("articles.author.empty")).classes("mt-3 text-[13px] text-subtext")
        return
    with ui.column().classes("mt-4 w-full gap-2.5"):
        for article in items:
            with (
                ui.link(target=f"/author/edit/{article.id}")
                .classes("w-full no-underline rounded-control border border-border bg-panel px-4 py-3")
                .mark("own-article")
            ):
                with ui.row().classes("w-full flex-nowrap items-center justify-between gap-3"):
                    with ui.column().classes("min-w-0 gap-0"):
                        ui.label(article.title).classes("text-[14.5px] font-semibold text-text")
                        ui.label(
                            t("articles.author.updated", date=article.updated_at.strftime(t("common.dateFormat")))
                        ).classes("text-[12px] text-subtext")
                    with ui.row().classes("flex-nowrap items-center gap-1.5"):
                        for language in article.languages:
                            # A language code, not prose - the same in both UIs.
                            _badge(language.upper())
                        _badge(t(f"articles.visibility.{article.visibility}"), accent=article.visibility != "draft")


def _editor(auth_state: AuthState, article: ArticleRead | None) -> None:
    """The editor form for a new (`article is None`) or existing article.

    Args:
        auth_state: The (writer's) login state.
        article: The article being edited, or `None` for a new one.
    """
    assert auth_state.user is not None
    author_id = auth_state.user.id
    article_id = article.id if article else None
    state = {"busy": False}

    ui.link(t("articles.author.backToMine"), "/author").classes("text-[13px] text-accent")
    ui.label(t("articles.editor.editTitle") if article else t("articles.editor.newTitle")).classes(
        "mt-3 text-[22px] font-bold text-text"
    )

    existing = {version.language: version for version in article.translations} if article else {}
    titles: dict[str, ui.input] = {}
    editors: dict[str, ui.editor] = {}
    tabs_by_language: dict[str, ui.tab] = {}

    def refresh_tab_label(language: str) -> None:
        """Marks a language tab whose version has no title yet as empty."""
        name = t(f"articles.languages.{language}")
        filled = (titles[language].value or "").strip()
        tab = tabs_by_language[language]
        tab.props["label"] = name if filled else f"{name} ({t('articles.editor.emptyVersion')})"
        tab.update()

    with ui.column().classes("mt-4 w-full gap-3"):
        ui.label(t("articles.editor.languagesHint")).classes("text-[12.5px] text-subtext")
        with ui.tabs().props("dense no-caps align=left").classes("w-full text-text") as tabs:
            for language in ARTICLE_LANGUAGES:
                tabs_by_language[language] = ui.tab(language, label=t(f"articles.languages.{language}")).mark(
                    f"article-tab-{language}"
                )
        # Opens on the version the reader-facing title came from: the UI
        # language's if the article has it (always, for a new article).
        with ui.tab_panels(tabs, value=article.language if article else current_language()).classes(
            "w-full bg-transparent"
        ) as panels:
            for language in ARTICLE_LANGUAGES:
                version = existing.get(language)
                with ui.tab_panel(language).classes("w-full gap-3 p-0 pt-2"):
                    titles[language] = (
                        ui.input(
                            t("articles.editor.titleLabel"),
                            value=version.title if version else "",
                            on_change=lambda _, language=language: refresh_tab_label(language),
                        )
                        .props("outlined dense maxlength=200")
                        .classes("w-full")
                        .mark(f"article-title-input-{language}")
                    )
                    editor = (
                        ui.editor(
                            value=version.content_html if version else "", placeholder=t("articles.editor.placeholder")
                        )
                        .classes("article-body w-full bg-panel")
                        .mark(f"article-editor-{language}")
                    )
                    editor.props["toolbar"] = _TOOLBAR_GROUPS
                    editor.props["min-height"] = "18rem"
                    editors[language] = editor
        for language in ARTICLE_LANGUAGES:
            refresh_tab_label(language)

        with ui.column().classes("w-full gap-1 rounded-control border border-border bg-panel px-3.5 py-3"):
            ui.label(t("articles.visibility.label")).classes(
                "text-[12px] font-bold uppercase tracking-wide text-subtext"
            )
            visibility = (
                ui.radio(
                    {value: t(f"articles.visibility.{value}") for value in VISIBILITIES},
                    value=article.visibility if article else "draft",
                )
                .props("inline dense")
                .classes("text-[13.5px] text-text")
                .mark("article-visibility")
            )
            recipients_box = ui.column().classes("w-full gap-1 pt-2")
            with recipients_box:
                recipients = (
                    ui.textarea(
                        t("articles.editor.recipientsLabel"), value="\n".join(article.recipients) if article else ""
                    )
                    .props("outlined dense autogrow")
                    .classes("w-full")
                    .mark("article-recipients")
                )
                ui.label(t("articles.editor.recipientsHint")).classes("text-[12px] text-subtext")
            recipients_box.bind_visibility_from(visibility, "value", backward=lambda value: value == "restricted")

        error_label = ui.label().classes("text-[12.5px] text-flag")
        error_label.set_visibility(False)

        async def save() -> None:
            nonlocal article_id
            if state["busy"]:
                return
            state["busy"] = True
            save_button.set_enabled(False)
            error_label.set_visibility(False)
            draft = ArticleDraft(
                translations=[
                    ArticleTranslation(
                        language=language,
                        title=titles[language].value or "",
                        content_html=editors[language].value or "",
                    )
                    for language in ARTICLE_LANGUAGES
                ],
                visibility=visibility.value,
                recipients=split_recipients(recipients.value or ""),
            )
            outcome = await articles_state.save_article(author_id, draft, article_id)
            state["busy"] = False
            save_button.set_enabled(True)
            if not outcome.ok:
                detail = outcome.detail
                if outcome.error == "missing_title":
                    panels.set_value(detail)  # show the version lacking it
                    detail = t(f"articles.languages.{detail}")
                error_label.set_text(error_text("articles", outcome.error, detail))
                error_label.set_visibility(True)
                return
            ui.notify(t("articles.editor.saved") if draft.visibility == "draft" else t("articles.editor.published"))
            if article_id is None:
                # From now on saves update this article - and a reload keeps it.
                ui.navigate.to(f"/author/edit/{outcome.value.id}")
            article_id = outcome.value.id

        async def delete() -> None:
            confirm.close()
            if article_id is None:
                return
            outcome = await articles_state.remove_article(author_id, article_id)
            if not outcome.ok:
                error_label.set_text(error_text("articles", outcome.error, outcome.detail))
                error_label.set_visibility(True)
                return
            ui.notify(t("articles.editor.deleted"))
            ui.navigate.to("/author")

        with ui.dialog() as confirm, ui.card().classes("rounded-card border border-border bg-panel p-5 gap-3"):
            ui.label(t("articles.editor.confirmDelete", title=article.title if article else "")).classes(
                "text-[14px] text-text"
            )
            with ui.row().classes("w-full justify-end gap-2"):
                ui.button(t("articles.editor.cancel"), on_click=confirm.close).props("flat no-caps").classes(
                    "text-[13px] text-subtext"
                )
                ui.button(t("articles.editor.delete"), on_click=delete).props("no-caps unelevated").classes(
                    "rounded-control bg-flag px-3.5 py-2 text-[13px] font-semibold text-accent-text"
                ).mark("confirm-delete")

        with ui.row().classes("w-full items-center gap-2"):
            save_button = (
                ui.button(on_click=save).props("no-caps unelevated").classes(_BUTTON_PRIMARY).mark("save-article")
            )
            save_button.bind_text_from(
                visibility,
                "value",
                backward=lambda value: (
                    t("articles.editor.saveDraft") if value == "draft" else t("articles.editor.publish")
                ),
            )
            if article is not None:
                ui.button(
                    t("articles.editor.view"),
                    icon="visibility",
                    on_click=lambda: ui.navigate.to(f"/articles/{article.id}"),
                ).props("flat no-caps").classes(_BUTTON_SECONDARY)
                ui.button(t("articles.editor.delete"), icon="delete", on_click=confirm.open).props(
                    "flat no-caps"
                ).classes("ml-auto text-[13px] text-flag").mark("delete-article")


def _error_block(code: str, detail: str = "") -> None:
    ui.label(error_text("articles", code, detail)).classes("text-[14px] text-flag")


async def _load_auth() -> AuthState:
    register_styles()
    auth_state = AuthState()
    await auth_state.refresh()
    return auth_state


def register_articles_pages() -> None:
    """Registers the portal's `@ui.page`s as a side effect - called once
    from `app/main.py`."""

    @ui.page("/articles", viewport=MOBILE_VIEWPORT, title=t("articles.pageTitle"))
    async def articles_list() -> None:
        auth_state = await _load_auth()
        outcome = await articles_state.list_visible(auth_state.user.id if auth_state.user else None)
        with _page_shell(auth_state):
            if outcome.ok:
                _articles_list(auth_state, outcome.value)
            else:
                _error_block(outcome.error)

    @ui.page("/articles/{article_id}", viewport=MOBILE_VIEWPORT, title=t("articles.pageTitle"))
    async def article_detail(article_id: int) -> None:
        auth_state = await _load_auth()
        outcome = await articles_state.get_for_reader(article_id, auth_state.user.id if auth_state.user else None)
        with _page_shell(auth_state):
            if not outcome.ok:
                _error_block(outcome.error)
            elif outcome.value is None:
                ui.label(t("articles.notFound")).classes("text-[17px] font-bold text-text")
                if auth_state.user is None:
                    ui.label(t("articles.notFoundHint")).classes("mt-1 text-[13px] text-subtext")
                ui.link(t("articles.backToList"), "/articles").classes("mt-3 text-[13px] text-accent")
            else:
                _article_view(auth_state, outcome.value)

    async def _writer_page(build: Callable[[AuthState], Awaitable[None]]) -> None:
        """Builds an author page, or the "no rights" note for non-writers -
        `build` never runs for them, so none of its handlers exist."""
        auth_state = await _load_auth()
        with _page_shell(auth_state):
            if not auth_state.can_write_articles:
                _not_allowed(auth_state)
                return
            await build(auth_state)

    @ui.page("/author", viewport=MOBILE_VIEWPORT, title=t("articles.author.pageTitle"))
    async def author_home() -> None:
        async def build(auth_state: AuthState) -> None:
            outcome = await articles_state.list_own(auth_state.user.id)
            if outcome.ok:
                _own_list(outcome.value)
            else:
                _error_block(outcome.error)

        await _writer_page(build)

    @ui.page("/author/new", viewport=MOBILE_VIEWPORT, title=t("articles.author.pageTitle"))
    async def author_new() -> None:
        async def build(auth_state: AuthState) -> None:
            _editor(auth_state, None)

        await _writer_page(build)

    @ui.page("/author/edit/{article_id}", viewport=MOBILE_VIEWPORT, title=t("articles.author.pageTitle"))
    async def author_edit(article_id: int) -> None:
        async def build(auth_state: AuthState) -> None:
            outcome = await articles_state.get_for_edit(auth_state.user.id, article_id)
            if outcome.ok:
                _editor(auth_state, outcome.value)
            else:
                _error_block(outcome.error)

        await _writer_page(build)

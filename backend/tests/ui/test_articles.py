"""The author role and the articles portal end to end, through NiceGUI's
headless `user` fixture: asking for the role from the account menu, an
admin approving it, writing and publishing an article in the editor, and
who gets to read it.
"""

import asyncio
from datetime import UTC, datetime
from pathlib import Path

import pytest
from nicegui import ui
from nicegui.testing import User
from sqlalchemy.orm import Session

from app.models.article import Article
from app.models.user import User as UserRow
from app.schemas.article import ArticleDraft, ArticleTranslation
from app.services import articles, authors

pytestmark = [
    pytest.mark.usefixtures("patch_ui_session"),
    pytest.mark.nicegui_main_file(str(Path(__file__).with_name("_user_main.py"))),
]


def _author(session: Session, email: str = "author@example.cz") -> UserRow:
    row = UserRow(
        email=email,
        is_admin=False,
        is_author=True,
        display_name="Jana Nová",
        is_active=True,
        created_at=datetime.now(UTC),
    )
    session.add(row)
    session.commit()
    return row


def _draft(
    title: str, content_html: str, visibility: str, recipients: list[str] | None = None, *, language: str = "cs"
) -> ArticleDraft:
    return ArticleDraft(
        translations=[ArticleTranslation(language=language, title=title, content_html=content_html)],
        visibility=visibility,
        recipients=recipients or [],
    )


def _set(user: User, marker: str, value: object) -> None:
    """Sets a value element directly - the simulated `type()` doesn't
    reach a QEditor or a radio group."""
    for element in user.find(marker=marker).elements:
        element.value = value


async def _wait_for(condition, tries: int = 100) -> bool:
    for _ in range(tries):
        if condition():
            return True
        await asyncio.sleep(0.02)
    return False


async def test_user_requests_role_and_admin_approves(user: User, log_in, patch_ui_session: Session) -> None:
    await user.open("/")
    await log_in(user, "writer@example.cz")

    user.find(marker="menu-become-author").click()
    await user.should_see("Stát se autorem", retries=100)
    user.find(marker="author-name").type("Jana Nová")
    user.find(marker="author-request-submit").click()
    await user.should_see(marker="author-request-sent", retries=100)

    writer = patch_ui_session.query(UserRow).filter_by(email="writer@example.cz").one()
    assert authors.latest_request(patch_ui_session, writer.id).status == "pending"

    user.find(marker="logout").click()
    await user.open("/")
    await log_in(user, "boss@example.cz", admin=True)
    await user.open("/admin")
    user.find("Autoři").click()
    await user.should_see("Jana Nová · writer@example.cz", retries=100)
    user.find(marker="approve-author").click()

    assert await _wait_for(lambda: (patch_ui_session.refresh(writer), writer.is_author)[1])
    assert writer.display_name == "Jana Nová"


async def test_regular_user_cannot_open_author_pages(user: User, log_in) -> None:
    await user.open("/")
    await log_in(user, "plain@example.cz")
    await user.open("/author/new")
    await user.should_see("Tato stránka je jen pro autory.")
    await user.should_not_see(marker="save-article")


async def test_author_publishes_article_to_everyone(user: User, log_in, patch_ui_session: Session) -> None:
    _author(patch_ui_session)
    await user.open("/")
    await log_in(user, "author@example.cz")
    user.find(marker="account-menu").click()
    user.find(marker="menu-my-articles").click()
    await user.should_see("Moje články", retries=100)

    await user.open("/author/new")
    user.find(marker="article-title-input-cs").type("Jak vybrat SUV")
    _set(user, "article-editor-cs", "<h2>Úvod</h2><p>Text článku.</p>")
    _set(user, "article-visibility", "public")
    await user.should_see("Publikovat")
    user.find(marker="save-article").click()

    assert await _wait_for(lambda: patch_ui_session.query(Article).count() == 1)
    article = patch_ui_session.query(Article).one()
    assert article.visibility == "public"
    (version,) = articles.get_for_edit(patch_ui_session, article.author_id, article.id).translations
    assert (version.language, version.content_html) == ("cs", "<h2>Úvod</h2><p>Text článku.</p>")

    await user.open("/articles")
    await user.should_see("Jak vybrat SUV", retries=100)


async def test_anonymous_reader_sees_public_but_not_restricted(user: User, patch_ui_session: Session) -> None:
    author = _author(patch_ui_session)
    public = articles.save(patch_ui_session, author.id, _draft("Veřejný", "<p>Pro všechny</p>", "public"))
    restricted = articles.save(
        patch_ui_session,
        author.id,
        _draft("Tajný", "<p>Jen pro Petra</p>", "restricted", ["petr@example.cz"]),
    )

    await user.open("/articles")
    await user.should_see("Veřejný", retries=100)
    await user.should_not_see("Tajný")

    await user.open(f"/articles/{public.id}")
    await user.should_see(marker="article-body", retries=100)
    assert user.find(kind=ui.html, marker="article-body").elements.pop().content == "<p>Pro všechny</p>"

    await user.open(f"/articles/{restricted.id}")
    await user.should_see("Článek neexistuje, nebo k němu nemáte přístup.", retries=100)


async def test_recipient_sees_restricted_article(user: User, log_in, patch_ui_session: Session) -> None:
    author = _author(patch_ui_session)
    restricted = articles.save(
        patch_ui_session,
        author.id,
        _draft("Tajný", "<p>Jen pro Petra</p>", "restricted", ["petr@example.cz"]),
    )

    await user.open("/")
    await log_in(user, "petr@example.cz")
    await user.open("/articles")
    await user.should_see("Tajný", retries=100)
    await user.should_see("Sdíleno s vámi")
    await user.open(f"/articles/{restricted.id}")
    await user.should_see(marker="article-body", retries=100)


async def test_missing_language_version_shows_notice(user: User, patch_ui_session: Session) -> None:
    author = _author(patch_ui_session)
    english = articles.save(
        patch_ui_session, author.id, _draft("Choosing an SUV", "<p>Hi</p>", "public", language="en")
    )

    await user.open("/articles")
    await user.should_see("Choosing an SUV", retries=100)
    await user.should_see("Jen anglicky")
    await user.open(f"/articles/{english.id}")
    await user.should_see("Tento článek je zatím dostupný jen v angličtině.", retries=100)

    user.find(marker="language-toggle").click()
    await user.open(f"/articles/{english.id}")
    await user.should_see(marker="article-body", retries=100)
    await user.should_not_see(marker="article-language-notice")


async def test_author_writes_both_language_versions(user: User, log_in, patch_ui_session: Session) -> None:
    author = _author(patch_ui_session)
    await user.open("/")
    await log_in(user, "author@example.cz")
    await user.open("/author/new")
    user.find(marker="article-title-input-cs").type("Jak vybrat SUV")
    _set(user, "article-editor-cs", "<p>Česky</p>")
    user.find(marker="article-title-input-en").type("Choosing an SUV")
    _set(user, "article-editor-en", "<p>English</p>")
    user.find(marker="save-article").click()

    assert await _wait_for(lambda: patch_ui_session.query(Article).count() == 1)
    article = patch_ui_session.query(Article).one()
    versions = articles.get_for_edit(patch_ui_session, author.id, article.id).translations
    assert [(v.language, v.title) for v in versions] == [("cs", "Jak vybrat SUV"), ("en", "Choosing an SUV")]

    await user.open(f"/articles/{article.id}")
    await user.should_see("Read in English", retries=100)
    await user.should_not_see(marker="article-language-notice")

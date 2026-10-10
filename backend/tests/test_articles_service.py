from datetime import UTC, datetime

import pytest
from sqlalchemy.orm import Session

from app.models.user import User
from app.schemas.article import ArticleDraft, ArticleTranslation
from app.services import articles
from app.services.articles import ArticleError
from tests.conftest import SeededData


def _user(session: Session, email: str, *, author: bool = False, admin: bool = False) -> User:
    row = User(
        email=email,
        is_admin=admin,
        is_author=author,
        display_name="Jana Nová" if author else None,
        is_active=True,
        created_at=datetime.now(UTC),
    )
    session.add(row)
    session.commit()
    return row


def _draft(
    visibility: str = "draft",
    recipients: list[str] | None = None,
    title: str = "Test",
    english: tuple[str, str] | None = None,
) -> ArticleDraft:
    """A Czech article, plus an English version when `english` is
    `(title, content_html)`."""
    translations = [ArticleTranslation(language="cs", title=title, content_html="<p>Ahoj</p>")]
    if english is not None:
        translations.append(ArticleTranslation(language="en", title=english[0], content_html=english[1]))
    return ArticleDraft(translations=translations, visibility=visibility, recipients=recipients or [])


@pytest.fixture()
def db(seeded_session: SeededData) -> Session:
    return seeded_session.session


def test_draft_is_visible_only_to_its_author(db: Session) -> None:
    author = _user(db, "author@example.cz", author=True)
    reader = _user(db, "reader@example.cz")
    article = articles.save(db, author.id, _draft())

    assert articles.list_visible(db, None) == []
    assert articles.list_visible(db, reader.id) == []
    assert articles.get_for_reader(db, article.id, reader.id) is None
    assert articles.get_for_reader(db, article.id, author.id) is not None
    assert article.published_at is None
    assert [a.id for a in articles.list_own(db, author.id)] == [article.id]


def test_public_article_is_visible_to_everyone(db: Session) -> None:
    author = _user(db, "author@example.cz", author=True)
    article = articles.save(db, author.id, _draft("public"))

    listed = articles.list_visible(db, None)
    assert [a.id for a in listed] == [article.id]
    assert listed[0].author_name == "Jana Nová"
    read = articles.get_for_reader(db, article.id, None)
    assert read.content_html == "<p>Ahoj</p>"
    assert article.published_at is not None


def test_restricted_article_reaches_only_recipients(db: Session) -> None:
    author = _user(db, "author@example.cz", author=True)
    reader = _user(db, "reader@example.cz")
    stranger = _user(db, "stranger@example.cz")
    article = articles.save(db, author.id, _draft("restricted", [" Reader@Example.cz ", "later@example.cz"]))

    assert article.recipients == ["reader@example.cz", "later@example.cz"]
    assert [a.id for a in articles.list_visible(db, reader.id)] == [article.id]
    assert articles.list_visible(db, stranger.id) == []
    assert articles.list_visible(db, None) == []
    assert articles.get_for_reader(db, article.id, stranger.id) is None
    # A recipient reads it but doesn't learn who else got it.
    assert articles.get_for_reader(db, article.id, reader.id).recipients == []
    assert articles.get_for_reader(db, article.id, author.id).recipients == ["later@example.cz", "reader@example.cz"]


def test_unpublishing_keeps_the_first_publish_date(db: Session) -> None:
    author = _user(db, "author@example.cz", author=True)
    published = articles.save(db, author.id, _draft("public"))
    articles.save(db, author.id, _draft("draft"), published.id)
    assert articles.list_visible(db, None) == []
    again = articles.save(db, author.id, _draft("public"), published.id)
    assert again.published_at == published.published_at


def test_validation_errors(db: Session) -> None:
    author = _user(db, "author@example.cz", author=True)
    cases = [
        (_draft(title="   "), "missing_title"),
        (
            ArticleDraft(
                translations=[ArticleTranslation(language="cs", title=" ", content_html="<p><br></p>")],
                visibility="draft",
            ),
            "empty_title",
        ),
        (_draft(english=("", "<p>Hello</p>")), "missing_title"),
        (_draft(title="x" * 201), "title_too_long"),
        (_draft("restricted"), "no_recipients"),
        (_draft("restricted", ["not-an-email"]), "invalid_recipient"),
    ]
    for draft, code in cases:
        with pytest.raises(ArticleError) as exc:
            articles.save(db, author.id, draft)
        assert exc.value.code == code


def test_only_authors_and_admins_write_and_only_their_own(db: Session) -> None:
    author = _user(db, "author@example.cz", author=True)
    other = _user(db, "other@example.cz", author=True)
    plain = _user(db, "plain@example.cz")
    admin = _user(db, "boss@example.cz", admin=True)

    with pytest.raises(ArticleError) as exc:
        articles.save(db, plain.id, _draft())
    assert exc.value.code == "forbidden"
    assert articles.save(db, admin.id, _draft("public")).author_name is None

    article = articles.save(db, author.id, _draft("public"))
    for call in (
        lambda: articles.save(db, other.id, _draft(title="Hacked"), article.id),
        lambda: articles.get_for_edit(db, other.id, article.id),
        lambda: articles.remove(db, other.id, article.id),
    ):
        with pytest.raises(ArticleError) as exc:
            call()
        assert exc.value.code == "not_found"


def test_revoked_author_cannot_edit_but_articles_stay_published(db: Session) -> None:
    author = _user(db, "author@example.cz", author=True)
    article = articles.save(db, author.id, _draft("public"))
    author.is_author = False
    db.commit()

    with pytest.raises(ArticleError) as exc:
        articles.save(db, author.id, _draft(), article.id)
    assert exc.value.code == "forbidden"
    assert [a.id for a in articles.list_visible(db, None)] == [article.id]


def test_remove_deletes_article_and_recipients(db: Session) -> None:
    author = _user(db, "author@example.cz", author=True)
    article = articles.save(db, author.id, _draft("restricted", ["reader@example.cz"]))
    articles.remove(db, author.id, article.id)
    assert articles.list_own(db, author.id) == []
    assert articles.get_for_reader(db, article.id, author.id) is None


def test_reader_gets_their_language_or_the_one_there_is(db: Session) -> None:
    author = _user(db, "author@example.cz", author=True)
    both = articles.save(db, author.id, _draft("public", title="Česky", english=("English", "<p>Hello</p>")))
    czech_only = articles.save(db, author.id, _draft("public", title="Jen česky"))

    english = {a.id: a for a in articles.list_visible(db, None, "en")}
    assert (english[both.id].title, english[both.id].language) == ("English", "en")
    assert english[both.id].languages == ["cs", "en"]
    assert (english[czech_only.id].title, english[czech_only.id].language) == ("Jen česky", "cs")

    read = articles.get_for_reader(db, both.id, None, "en")
    assert read.content_html == "<p>Hello</p>"
    assert read.translations == []  # a reader doesn't get the editor's view
    assert articles.get_for_reader(db, both.id, None, "cs").title == "Česky"
    assert articles.get_for_reader(db, czech_only.id, None, "en").language == "cs"


def test_emptied_language_version_is_dropped(db: Session) -> None:
    author = _user(db, "author@example.cz", author=True)
    article = articles.save(db, author.id, _draft(english=("English", "<p>Hello</p>")))
    assert [v.language for v in articles.get_for_edit(db, author.id, article.id).translations] == ["cs", "en"]

    articles.save(db, author.id, _draft(english=("", "<br>")), article.id)
    edited = articles.get_for_edit(db, author.id, article.id, "en")
    assert [v.language for v in edited.translations] == ["cs"]
    assert edited.language == "cs"


def test_english_only_article(db: Session) -> None:
    author = _user(db, "author@example.cz", author=True)
    draft = ArticleDraft(
        translations=[
            ArticleTranslation(language="cs", title="", content_html=""),
            ArticleTranslation(language="en", title="Only English", content_html="<p>Hi</p>"),
        ],
        visibility="public",
    )
    article = articles.save(db, author.id, draft)
    assert article.languages == ["en"]
    assert articles.get_for_reader(db, article.id, None, "cs").title == "Only English"

from datetime import UTC, datetime

import pytest
from sqlalchemy.orm import Session

from app.models.user import User
from app.services import authors
from app.services.authors import AuthorError
from tests.conftest import SeededData


def _user(session: Session, email: str, *, admin: bool = False, author: bool = False) -> User:
    row = User(email=email, is_admin=admin, is_author=author, is_active=True, created_at=datetime.now(UTC))
    session.add(row)
    session.commit()
    return row


@pytest.fixture()
def db(seeded_session: SeededData) -> Session:
    return seeded_session.session


def test_request_then_approve_grants_role_and_byline(db: Session) -> None:
    admin = _user(db, "boss@example.cz", admin=True)
    writer = _user(db, "writer@example.cz")

    request = authors.request_role(db, writer.id, "  Jana Nová ", "Píšu o elektromobilech.")
    assert request.status == "pending"
    assert [r.id for r in authors.list_pending(db, admin.id)] == [request.id]

    authors.decide(db, admin.id, request.id, approve=True)

    db.refresh(writer)
    assert writer.is_author and writer.display_name == "Jana Nová"
    assert authors.list_pending(db, admin.id) == []
    assert authors.latest_request(db, writer.id).status == "approved"
    assert [a.email for a in authors.list_authors(db, admin.id)] == ["writer@example.cz"]


def test_reject_leaves_user_without_role_and_lets_them_ask_again(db: Session) -> None:
    admin = _user(db, "boss@example.cz", admin=True)
    writer = _user(db, "writer@example.cz")
    request = authors.request_role(db, writer.id, "Jana")

    authors.decide(db, admin.id, request.id, approve=False)

    db.refresh(writer)
    assert not writer.is_author
    with pytest.raises(AuthorError) as exc:
        authors.decide(db, admin.id, request.id, approve=True)
    assert exc.value.code == "already_decided"
    assert authors.request_role(db, writer.id, "Jana").status == "pending"


def test_second_pending_request_is_refused(db: Session) -> None:
    writer = _user(db, "writer@example.cz")
    authors.request_role(db, writer.id, "Jana")
    with pytest.raises(AuthorError) as exc:
        authors.request_role(db, writer.id, "Jana")
    assert exc.value.code == "already_pending"


def test_author_cannot_request_again_and_blank_name_is_refused(db: Session) -> None:
    author = _user(db, "author@example.cz", author=True)
    plain = _user(db, "plain@example.cz")
    with pytest.raises(AuthorError) as exc:
        authors.request_role(db, author.id, "Jana")
    assert exc.value.code == "already_author"
    with pytest.raises(AuthorError) as exc:
        authors.request_role(db, plain.id, "   ")
    assert exc.value.code == "invalid_name"


def test_admin_actions_require_an_admin(db: Session) -> None:
    writer = _user(db, "writer@example.cz")
    request = authors.request_role(db, writer.id, "Jana")
    for call in (
        lambda: authors.list_pending(db, writer.id),
        lambda: authors.decide(db, writer.id, request.id, approve=True),
        lambda: authors.list_authors(db, writer.id),
        lambda: authors.revoke(db, writer.id, writer.id),
    ):
        with pytest.raises(AuthorError) as exc:
            call()
        assert exc.value.code == "forbidden"
    db.refresh(writer)
    assert not writer.is_author


def test_revoke_removes_role(db: Session) -> None:
    admin = _user(db, "boss@example.cz", admin=True)
    author = _user(db, "author@example.cz", author=True)
    authors.revoke(db, admin.id, author.id)
    db.refresh(author)
    assert not author.is_author

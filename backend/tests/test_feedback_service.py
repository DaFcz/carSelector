from datetime import UTC, datetime

import pytest
from sqlalchemy.orm import Session

from app.core.version import app_version
from app.models.user import User
from app.schemas.feedback import FeedbackContext
from app.schemas.requirement import StructuredRequirements
from app.services import feedback
from app.services.feedback import MAX_PER_DAY, FeedbackError
from tests.conftest import SeededData


def _user(session: Session, email: str, *, admin: bool = False, active: bool = True) -> User:
    row = User(email=email, is_admin=admin, is_active=active, created_at=datetime.now(UTC))
    session.add(row)
    session.commit()
    return row


@pytest.fixture()
def db(seeded_session: SeededData) -> Session:
    return seeded_session.session


def test_submit_then_admin_lists_and_resolves(db: Session) -> None:
    admin = _user(db, "boss@example.cz", admin=True)
    sender = _user(db, "jana@example.cz")
    context = FeedbackContext(page="search", app_version="0.3.4", requirements=StructuredRequirements(min_seats=7))

    item = feedback.submit(db, sender.id, "bug", "  Cena u Octavie nesedí. ", context, "cs")

    assert item.status == "new" and item.text == "Cena u Octavie nesedí."
    assert feedback.count_new(db, admin.id) == 1
    (listed,) = feedback.list_for_admin(db, admin.id)
    assert listed.email == "jana@example.cz"
    assert listed.context.requirements.min_seats == 7 and listed.context.app_version == "0.3.4"

    updated = feedback.update(db, admin.id, item.id, "resolved", " Opraveno v importu. ")

    assert updated.status == "resolved" and updated.admin_note == "Opraveno v importu."
    assert updated.updated_at is not None
    assert feedback.count_new(db, admin.id) == 0


def test_list_filters_by_type_and_status(db: Session) -> None:
    admin = _user(db, "boss@example.cz", admin=True)
    sender = _user(db, "jana@example.cz")
    bug = feedback.submit(db, sender.id, "bug", "Padá to.", FeedbackContext(), "cs")
    feedback.submit(db, sender.id, "praise", "Super!", FeedbackContext(), "en")
    feedback.update(db, admin.id, bug.id, "in_progress", "")

    assert [i.type for i in feedback.list_for_admin(db, admin.id, feedback_type="praise")] == ["praise"]
    assert [i.id for i in feedback.list_for_admin(db, admin.id, status="in_progress")] == [bug.id]
    assert [i.type for i in feedback.list_for_admin(db, admin.id)] == ["praise", "bug"]  # newest first


@pytest.mark.parametrize(
    ("feedback_type", "text", "code"),
    [("bug", "   ", "empty_text"), ("bug", "x" * 4001, "text_too_long"), ("complaint", "Hm.", "invalid_type")],
)
def test_submit_rejects_invalid_input(db: Session, feedback_type: str, text: str, code: str) -> None:
    sender = _user(db, "jana@example.cz")
    with pytest.raises(FeedbackError) as exc:
        feedback.submit(db, sender.id, feedback_type, text, FeedbackContext(), "cs")
    assert exc.value.code == code


def test_deactivated_user_cannot_submit(db: Session) -> None:
    sender = _user(db, "gone@example.cz", active=False)
    with pytest.raises(FeedbackError) as exc:
        feedback.submit(db, sender.id, "idea", "Nápad", FeedbackContext(), "cs")
    assert exc.value.code == "forbidden"


def test_submit_is_rate_limited_per_user(db: Session) -> None:
    sender = _user(db, "jana@example.cz")
    other = _user(db, "petr@example.cz")
    for n in range(MAX_PER_DAY):
        feedback.submit(db, sender.id, "idea", f"Nápad {n}", FeedbackContext(), "cs")

    with pytest.raises(FeedbackError) as exc:
        feedback.submit(db, sender.id, "idea", "Ještě jeden", FeedbackContext(), "cs")
    assert exc.value.code == "rate_limited"
    assert feedback.submit(db, other.id, "idea", "Můj nápad", FeedbackContext(), "cs").status == "new"


def test_admin_actions_need_an_admin(db: Session) -> None:
    sender = _user(db, "jana@example.cz")
    item = feedback.submit(db, sender.id, "bug", "Chyba", FeedbackContext(), "cs")
    for action in (
        lambda: feedback.list_for_admin(db, sender.id),
        lambda: feedback.count_new(db, sender.id),
        lambda: feedback.update(db, sender.id, item.id, "resolved", ""),
    ):
        with pytest.raises(FeedbackError) as exc:
            action()
        assert exc.value.code == "forbidden"


def test_update_rejects_unknown_status_and_item(db: Session) -> None:
    admin = _user(db, "boss@example.cz", admin=True)
    sender = _user(db, "jana@example.cz")
    item = feedback.submit(db, sender.id, "bug", "Chyba", FeedbackContext(), "cs")
    with pytest.raises(FeedbackError) as exc:
        feedback.update(db, admin.id, item.id, "closed", "")
    assert exc.value.code == "invalid_status"
    with pytest.raises(FeedbackError) as exc:
        feedback.update(db, admin.id, 999_999, "resolved", "")
    assert exc.value.code == "not_found"


def test_app_version_comes_from_the_changelog() -> None:
    version = app_version()
    assert version is not None and version.startswith("0.")

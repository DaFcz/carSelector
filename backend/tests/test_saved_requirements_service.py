from datetime import datetime, timezone

import pytest
from sqlalchemy.orm import Session

from app.models.saved_requirements import SavedRequirements
from app.models.user import User
from app.schemas.common import Money
from app.schemas.requirement import StructuredRequirements
from app.services import saved_requirements


@pytest.fixture()
def user(db_session: Session) -> User:
    row = User(email="driver@example.cz", is_admin=False, is_active=True, created_at=datetime.now(timezone.utc))
    db_session.add(row)
    db_session.commit()
    return row


def test_load_returns_none_when_nothing_saved(db_session: Session, user: User) -> None:
    assert saved_requirements.load(db_session, user.id) is None


def test_save_then_load_round_trips(db_session: Session, user: User) -> None:
    requirements = StructuredRequirements(body_type="SUV", fuel_type="electric", budget_max=Money(amount=900000, currency="CZK"))

    saved_requirements.save(db_session, user.id, requirements)

    assert saved_requirements.load(db_session, user.id) == requirements


def test_save_overwrites_the_previous_snapshot_instead_of_adding_a_row(db_session: Session, user: User) -> None:
    saved_requirements.save(db_session, user.id, StructuredRequirements(body_type="SUV"))
    saved_requirements.save(db_session, user.id, StructuredRequirements(body_type="Kombi"))

    assert saved_requirements.load(db_session, user.id) == StructuredRequirements(body_type="Kombi")
    assert db_session.query(SavedRequirements).filter(SavedRequirements.user_id == user.id).count() == 1


def test_save_is_scoped_per_user(db_session: Session, user: User) -> None:
    other = User(email="other@example.cz", is_admin=False, is_active=True, created_at=datetime.now(timezone.utc))
    db_session.add(other)
    db_session.commit()

    saved_requirements.save(db_session, user.id, StructuredRequirements(body_type="SUV"))

    assert saved_requirements.load(db_session, other.id) is None


def test_clear_removes_the_saved_snapshot(db_session: Session, user: User) -> None:
    saved_requirements.save(db_session, user.id, StructuredRequirements(body_type="SUV"))

    saved_requirements.clear(db_session, user.id)

    assert saved_requirements.load(db_session, user.id) is None


def test_clear_is_a_noop_when_nothing_was_saved(db_session: Session, user: User) -> None:
    saved_requirements.clear(db_session, user.id)  # must not raise

    assert saved_requirements.load(db_session, user.id) is None

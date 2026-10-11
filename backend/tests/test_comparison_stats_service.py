from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.car_model import CarModel
from app.models.comparison_view import ComparisonView
from app.models.user import User
from app.services import comparison_stats
from app.services.comparison_stats import ComparisonStatsError
from tests.conftest import SeededData


@pytest.fixture()
def db(seeded_session: SeededData) -> Session:
    return seeded_session.session


def _admin(session: Session, *, admin: bool = True) -> int:
    row = User(email="boss@example.cz", is_admin=admin, is_active=True, created_at=datetime.now(UTC))
    session.add(row)
    session.commit()
    return row.id


def _third_model(session: Session) -> int:
    model = CarModel(id=3, brand_id=2, slug="tayron", name="Tayron")
    session.add(model)
    session.commit()
    return model.id


def test_a_single_car_is_not_a_comparison(db: Session, seeded_session: SeededData) -> None:
    assert not comparison_stats.record(db, [seeded_session.model_id])
    assert db.scalar(select(func.count(ComparisonView.id))) == 0


def test_most_compared_ranks_models_and_their_partners(db: Session, seeded_session: SeededData) -> None:
    mazda, tiguan, tayron = seeded_session.model_id, seeded_session.vw_model_id, _third_model(db)
    comparison_stats.record(db, [mazda, tiguan])
    comparison_stats.record(db, [mazda, tiguan, tayron])
    comparison_stats.record(db, [tiguan, tiguan])  # two Tiguan trims
    comparison_stats.record(db, [tiguan, tayron])

    stats = comparison_stats.most_compared(db, _admin(db))

    assert stats.total == 4
    assert [(m.model, m.comparisons) for m in stats.models] == [("Tiguan", 4), ("CX-5", 2), ("Tayron", 2)]
    tiguan_stat = stats.models[0]
    assert tiguan_stat.brand == "Volkswagen" and tiguan_stat.within_model == 1
    # Ties broken by brand and name: Mazda CX-5 before Volkswagen Tayron.
    assert [(p.model, p.count) for p in tiguan_stat.partners] == [("CX-5", 2), ("Tayron", 2)]
    assert [(p.model, p.count) for p in stats.models[1].partners] == [("Tiguan", 2), ("Tayron", 1)]


def test_period_and_limits(db: Session, seeded_session: SeededData) -> None:
    mazda, tiguan, tayron = seeded_session.model_id, seeded_session.vw_model_id, _third_model(db)
    now = datetime.now(UTC)
    comparison_stats.record(db, [mazda, tayron], now=now - timedelta(days=40))
    comparison_stats.record(db, [mazda, tiguan], now=now)
    admin_id = _admin(db)

    recent = comparison_stats.most_compared(db, admin_id, since=now - timedelta(days=30))
    assert recent.total == 1
    assert {m.model for m in recent.models} == {"CX-5", "Tiguan"}

    top = comparison_stats.most_compared(db, admin_id, limit=1, partner_limit=1)
    assert [(m.model, [p.model for p in m.partners]) for m in top.models] == [("CX-5", ["Tayron"])]


def test_empty_statistic(db: Session) -> None:
    stats = comparison_stats.most_compared(db, _admin(db))
    assert stats.total == 0 and stats.models == []


def test_only_admins_read_it(db: Session) -> None:
    with pytest.raises(ComparisonStatsError) as error:
        comparison_stats.most_compared(db, _admin(db, admin=False))
    assert error.value.code == "forbidden"

"""Which car models users compare, and with which - the admin console's
"Porovnání" statistic.

`record` stores one row per comparison a user actually displayed (2+
cars, see `app/ui/components/compare_dialog.py`), broken down by car
model; `most_compared` aggregates them. Anonymous by design - no user id
is kept, see `app/models/comparison_view.py`.

Reading the statistic re-checks, against the DB, that the acting user is
an active admin - same as `app/services/feedback.py`.
"""

from collections import Counter, defaultdict
from collections.abc import Iterable
from datetime import UTC, datetime

from sqlalchemy import and_, case, func, select
from sqlalchemy.orm import Session, aliased

from app.models.brand import Brand
from app.models.car_model import CarModel
from app.models.comparison_view import ComparisonView, ComparisonViewModel
from app.models.user import User
from app.schemas.comparison_stats import ComparedModelStat, ComparisonPartner, ComparisonStats

# Fewer cars than this isn't a comparison - mirrors `app/ui/compare.py`'s
# `MIN_COMPARE` (not imported: services don't depend on the UI layer).
MIN_CARS = 2


class ComparisonStatsError(Exception):
    """Reading the statistic was refused.

    Attributes:
        code: `"forbidden"`. Stable; the UI maps it to text under
            `comparisonStats.errors`.
    """

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _require_admin(db: Session, admin_id: int) -> None:
    admin = db.get(User, admin_id)
    if admin is None or not admin.is_active or not admin.is_admin:
        raise ComparisonStatsError("forbidden")


def record(db: Session, model_ids: Iterable[int], now: datetime | None = None) -> bool:
    """Stores one displayed comparison.

    Args:
        db: Session to write through; committed here.
        model_ids: The car model of each compared car, one entry per car
            (a model compared in two trims appears twice).
        now: When it happened; defaults to the current time.

    Returns:
        Whether it was stored - fewer than `MIN_CARS` cars isn't a
        comparison and is skipped.
    """
    cars_per_model = Counter(model_ids)
    if sum(cars_per_model.values()) < MIN_CARS:
        return False
    view = ComparisonView(created_at=now or datetime.now(UTC))
    db.add(view)
    db.flush()
    db.add_all(
        ComparisonViewModel(view_id=view.id, model_id=model_id, cars=cars) for model_id, cars in cars_per_model.items()
    )
    db.commit()
    return True


def most_compared(
    db: Session, admin_id: int, since: datetime | None = None, limit: int = 20, partner_limit: int = 5
) -> ComparisonStats:
    """Args:
        db: Session to read through.
        admin_id: The acting admin.
        since: Only count comparisons from this moment on; `None` = all.
        limit: How many of the most compared models to return.
        partner_limit: How many partners to return per model.

    Returns:
        The most compared models (ties broken by name), each with the
        models it was most often compared with.

    Raises:
        ComparisonStatsError: `"forbidden"` if `admin_id` isn't an active
            admin.
    """
    _require_admin(db, admin_id)
    in_period = [ComparisonView.created_at >= since] if since is not None else []

    total = db.scalar(select(func.count(ComparisonView.id)).where(*in_period)) or 0

    top = db.execute(
        select(
            ComparisonViewModel.model_id,
            func.count(ComparisonViewModel.id),
            func.sum(case((ComparisonViewModel.cars >= MIN_CARS, 1), else_=0)),
        )
        .join(ComparisonView, ComparisonView.id == ComparisonViewModel.view_id)
        .where(*in_period)
        .group_by(ComparisonViewModel.model_id)
    ).all()
    if not top:
        return ComparisonStats(total=total, models=[])

    this, other = aliased(ComparisonViewModel), aliased(ComparisonViewModel)
    partners: dict[int, Counter[int]] = defaultdict(Counter)
    for model_id, partner_id, count in db.execute(
        select(this.model_id, other.model_id, func.count())
        .join(other, and_(other.view_id == this.view_id, other.model_id != this.model_id))
        .join(ComparisonView, ComparisonView.id == this.view_id)
        .where(*in_period)
        .group_by(this.model_id, other.model_id)
    ):
        partners[model_id][partner_id] = count

    names = {
        model_id: (brand, model)
        for model_id, brand, model in db.execute(
            select(CarModel.id, Brand.name, CarModel.name)
            .join(Brand, Brand.id == CarModel.brand_id)
            .where(CarModel.id.in_({row[0] for row in top} | {p for c in partners.values() for p in c}))
        )
    }

    def _name(model_id: int) -> tuple[str, str]:
        return names.get(model_id, ("?", str(model_id)))

    def _partners(model_id: int) -> list[ComparisonPartner]:
        ranked = sorted(partners[model_id].items(), key=lambda item: (-item[1], _name(item[0])))
        return [
            ComparisonPartner(model_id=partner_id, brand=_name(partner_id)[0], model=_name(partner_id)[1], count=count)
            for partner_id, count in ranked[:partner_limit]
        ]

    ranked = sorted(top, key=lambda row: (-row[1], _name(row[0])))[:limit]
    return ComparisonStats(
        total=total,
        models=[
            ComparedModelStat(
                model_id=model_id,
                brand=_name(model_id)[0],
                model=_name(model_id)[1],
                comparisons=count,
                within_model=int(within or 0),
                partners=_partners(model_id),
            )
            for model_id, count, within in ranked
        ],
    )

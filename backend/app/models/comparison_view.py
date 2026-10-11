from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, SmallInteger, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, BigIntPK


class ComparisonView(Base):
    """One displayed comparison of 2+ cars - see
    `app/services/comparison_stats.py`.

    Deliberately anonymous (no user id): the statistic is about which cars
    get compared with which, not about who compared them.
    """

    __tablename__ = "comparison_views"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)


class ComparisonViewModel(Base):
    """One car model (`models` row) taking part in a `ComparisonView`.

    Per model, not per configuration: the statistic is "which models are
    compared with which". `cars` keeps how many of the compared cars were
    this model, so a comparison of one model's trims (`cars >= 2`) still
    shows up.
    """

    __tablename__ = "comparison_view_models"
    __table_args__ = (UniqueConstraint("view_id", "model_id"),)

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True)
    view_id: Mapped[int] = mapped_column(ForeignKey("comparison_views.id"), nullable=False)
    model_id: Mapped[int] = mapped_column(ForeignKey("models.id"), nullable=False, index=True)
    cars: Mapped[int] = mapped_column(SmallInteger, nullable=False)

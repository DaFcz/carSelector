from typing import TYPE_CHECKING

from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, BigIntPK
from app.models.enums import OptionCategory

if TYPE_CHECKING:
    from app.models.car_model import CarModel
    from app.models.option_availability import OptionAvailability


class OptionItem(Base):
    """Catalog of equipment features, packages, extended warranties and
    service packages that can be standard/optional/unavailable per
    configuration - the open-ended long tail (contrast with `colors`,
    which is a small, universal, dedicated table).
    """

    __tablename__ = "option_items"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True)
    model_id: Mapped[int] = mapped_column(ForeignKey("models.id"), nullable=False)
    category: Mapped[OptionCategory] = mapped_column(
        SAEnum(OptionCategory, name="option_category"), nullable=False
    )
    # VW's "WBQ"/"PL5"-style codes; null for Mazda, which names items
    # without an internal SKU code in the consumer-facing brochure.
    code: Mapped[str | None] = mapped_column(String(32))
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)

    model: Mapped["CarModel"] = relationship(back_populates="option_items")
    availabilities: Mapped[list["OptionAvailability"]] = relationship(back_populates="option_item")

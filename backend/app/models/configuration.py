from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, BigIntPK

if TYPE_CHECKING:
    from app.models.configuration_color import ConfigurationColor
    from app.models.option_availability import OptionAvailability
    from app.models.powertrain import Powertrain
    from app.models.price import Price
    from app.models.trim import Trim


class Configuration(Base):
    """The actual sellable unit: one trim sold with one powertrain.

    Populated from whatever the source document lists as orderable - never
    computed as a full trim x powertrain cross product, since not every
    trim offers every engine (this varies by brand; see design notes).
    """

    __tablename__ = "configurations"
    __table_args__ = (UniqueConstraint("trim_id", "powertrain_id"),)

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True)
    trim_id: Mapped[int] = mapped_column(ForeignKey("trims.id"), nullable=False)
    powertrain_id: Mapped[int] = mapped_column(ForeignKey("powertrains.id"), nullable=False)
    # Populated for VW; null for Mazda, which exposes no order code in the
    # consumer-facing price list.
    manufacturer_code: Mapped[str | None] = mapped_column(String(32))

    trim: Mapped["Trim"] = relationship(back_populates="configurations")
    powertrain: Mapped["Powertrain"] = relationship(back_populates="configurations")
    prices: Mapped[list["Price"]] = relationship(back_populates="configuration")
    option_availabilities: Mapped[list["OptionAvailability"]] = relationship(back_populates="configuration")
    configuration_colors: Mapped[list["ConfigurationColor"]] = relationship(back_populates="configuration")

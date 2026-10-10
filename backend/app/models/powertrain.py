from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Integer,
    Numeric,
    SmallInteger,
    String,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, BigIntPK
from app.models.enums import ConsumptionUnit, Drivetrain, FuelType

if TYPE_CHECKING:
    from app.models.car_model import CarModel
    from app.models.configuration import Configuration


class Powertrain(Base):
    """An engine/motor definition, described once per model and shared
    across every trim that offers it (see `configurations` for the
    trim x powertrain sellable unit).
    """

    __tablename__ = "powertrains"
    __table_args__ = (
        CheckConstraint(
            "consumption_max IS NULL OR consumption_min IS NULL OR consumption_max >= consumption_min",
            name="consumption_max_gte_min",
        ),
        CheckConstraint(
            "co2_max_g_km IS NULL OR co2_min_g_km IS NULL OR co2_max_g_km >= co2_min_g_km",
            name="co2_max_gte_min",
        ),
    )

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True)
    model_id: Mapped[int] = mapped_column(ForeignKey("models.id"), nullable=False)
    # Populated for VW ("CT1C4ZP2"-style codes); Mazda's price list gives none.
    manufacturer_code: Mapped[str | None] = mapped_column(String(32))
    fuel_type: Mapped[FuelType] = mapped_column(SAEnum(FuelType, name="fuel_type"), nullable=False)
    transmission: Mapped[str | None] = mapped_column(String(64))
    drivetrain: Mapped[Drivetrain] = mapped_column(SAEnum(Drivetrain, name="drivetrain"), nullable=False)
    displacement_cc: Mapped[int | None] = mapped_column(Integer)
    cylinder_count: Mapped[int | None] = mapped_column(SmallInteger)
    power_kw: Mapped[int | None] = mapped_column(Integer)
    power_hp: Mapped[int | None] = mapped_column(Integer)
    torque_nm: Mapped[int | None] = mapped_column(Integer)
    top_speed_kmh: Mapped[int | None] = mapped_column(Integer)
    accel_0_100_s: Mapped[float | None] = mapped_column(Numeric(4, 1))
    # Ranges, not scalars: both source documents show a range on at least
    # one variant (e.g. PHEV dual-mode consumption/CO2 figures). When the
    # source gives a single value, min == max.
    consumption_min: Mapped[float | None] = mapped_column(Numeric(5, 2))
    consumption_max: Mapped[float | None] = mapped_column(Numeric(5, 2))
    consumption_unit: Mapped[ConsumptionUnit | None] = mapped_column(SAEnum(ConsumptionUnit, name="consumption_unit"))
    co2_min_g_km: Mapped[int | None] = mapped_column(Integer)
    co2_max_g_km: Mapped[int | None] = mapped_column(Integer)
    emission_standard: Mapped[str | None] = mapped_column(String(16))
    fuel_tank_l: Mapped[int | None] = mapped_column(Integer)

    model: Mapped["CarModel"] = relationship(back_populates="powertrains")
    configurations: Mapped[list["Configuration"]] = relationship(back_populates="powertrain")

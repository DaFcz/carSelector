from typing import TYPE_CHECKING

from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, BigIntPK
from app.models.enums import ColorFinish

if TYPE_CHECKING:
    from app.models.car_model import CarModel
    from app.models.configuration_color import ConfigurationColor


class Color(Base):
    __tablename__ = "colors"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True)
    model_id: Mapped[int] = mapped_column(ForeignKey("models.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    # VW's "0Q0Q"-style paint code; Mazda gives none.
    manufacturer_code: Mapped[str | None] = mapped_column(String(16))
    # Nullable: VW categorizes solid/metallic/pearlescent, Mazda's flat
    # list doesn't state this explicitly.
    finish_type: Mapped[ColorFinish | None] = mapped_column(SAEnum(ColorFinish, name="color_finish"))

    model: Mapped["CarModel"] = relationship(back_populates="colors")
    configuration_colors: Mapped[list["ConfigurationColor"]] = relationship(back_populates="color")

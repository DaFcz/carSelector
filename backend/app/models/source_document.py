from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Date, DateTime, ForeignKey, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, BigIntPK
from app.models.enums import DocumentType

if TYPE_CHECKING:
    from app.models.car_model import CarModel
    from app.models.price import Price


class SourceDocument(Base):
    """Provenance record for one scraped file (e.g. one manufacturer PDF
    price list), so every price row can be traced back to where it came
    from.

    Deliberately keeps three distinct "when" concepts separate: the
    document's own declared price-effective date, an optional promotional
    campaign order/delivery window (which can differ from the effective
    date - seen in the Mazda sample, where the campaign window is months
    later than the base price list's effective date), and the scraper's
    own retrieval timestamp.
    """

    __tablename__ = "source_documents"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True)
    model_id: Mapped[int] = mapped_column(ForeignKey("models.id"), nullable=False)
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    document_type: Mapped[DocumentType] = mapped_column(SAEnum(DocumentType, name="document_type"), nullable=False)
    market: Mapped[str] = mapped_column(String(8), nullable=False)
    locale: Mapped[str | None] = mapped_column(String(16))
    effective_date: Mapped[date] = mapped_column(Date, nullable=False)
    campaign_valid_from: Mapped[date | None] = mapped_column(Date)
    campaign_valid_to: Mapped[date | None] = mapped_column(Date)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    model: Mapped["CarModel"] = relationship(back_populates="source_documents")
    prices: Mapped[list["Price"]] = relationship(back_populates="source_document")

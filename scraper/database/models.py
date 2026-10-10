"""SQLAlchemy models matching the schema in
doc/arch/webScraping/Car_Price_List_Architecture.md.

Key principle for data verification: `Variant` and `PriceHistory` always
link back to `Document` (source_page, raw_text), so every extracted
number can be traced back to the page and exact text in the source PDF.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    Date,
    DateTime,
    Float,
    ForeignKey,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Document(Base):
    """A single downloaded PDF file (price list/equipment) with a hash for dedup."""

    __tablename__ = "document"
    __table_args__ = (UniqueConstraint("source_brand", "sha256_hash"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    source_brand: Mapped[str] = mapped_column(String(100))
    document_url: Mapped[str] = mapped_column(String)
    sha256_hash: Mapped[str] = mapped_column(String(64))
    file_path: Mapped[str] = mapped_column(String)  # local path to the stored PDF (for the parser)
    release_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    downloaded_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    variants: Mapped[list[Variant]] = relationship(back_populates="document")


class Variant(Base):
    """A specific vehicle variant extracted from a document (model + trim + powertrain)."""

    __tablename__ = "variant"

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("document.id"))
    brand: Mapped[str] = mapped_column(String(100))
    # "ICE" or "EV" — denormalized onto Variant (instead of joining through
    # Document/Source) so "all EVs" can be filtered with a single WHERE
    # across brands, even though the source PDF structure differs (see
    # parsers/base.py).
    powertrain: Mapped[str] = mapped_column(String(10))
    model: Mapped[str] = mapped_column(String(200))
    trim: Mapped[str | None] = mapped_column(String(200), nullable=True)
    variant_name: Mapped[str] = mapped_column(String(300))

    # verification: the exact location in the PDF and the raw text the record came from
    source_page: Mapped[int] = mapped_column()
    raw_text: Mapped[str] = mapped_column(String)

    document: Mapped[Document] = relationship(back_populates="variants")
    prices: Mapped[list[PriceHistory]] = relationship(back_populates="variant")
    equipment: Mapped[list[EquipmentAssignment]] = relationship(back_populates="variant")


class PriceHistory(Base):
    __tablename__ = "price_history"

    id: Mapped[int] = mapped_column(primary_key=True)
    variant_id: Mapped[int] = mapped_column(ForeignKey("variant.id"))
    document_id: Mapped[int] = mapped_column(ForeignKey("document.id"))
    price: Mapped[float] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(3), default="CZK")
    valid_from: Mapped[date] = mapped_column(Date)

    variant: Mapped[Variant] = relationship(back_populates="prices")


class Equipment(Base):
    """Canonical (normalized) equipment name — see normalization/equipment_alias.py."""

    __tablename__ = "equipment"

    id: Mapped[int] = mapped_column(primary_key=True)
    canonical_name: Mapped[str] = mapped_column(String(200), unique=True)


class EquipmentAssignment(Base):
    __tablename__ = "equipment_assignment"

    id: Mapped[int] = mapped_column(primary_key=True)
    variant_id: Mapped[int] = mapped_column(ForeignKey("variant.id"))
    equipment_id: Mapped[int] = mapped_column(ForeignKey("equipment.id"))
    availability: Mapped[str] = mapped_column(String(20))  # STANDARD/OPTIONAL/PACKAGE/NOT_AVAILABLE
    # Price of this item for this variant, when the source states one (e.g.
    # Škoda's "Samostatné prvky výbavy" page - see
    # parsers/skoda_equipment.py) - null when the source doesn't carry a
    # price (e.g. standard-equipment items, which aren't paid add-ons).
    surcharge_amount: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)

    variant: Mapped[Variant] = relationship(back_populates="equipment")

"""Stores parser output (ExtractedVariant) in the DB as Variant + PriceHistory.

Only called for documents that `fetch_new_documents` judged to be new
(see monitors/source_monitor.py) — thanks to that, idempotency/dedup
doesn't need to be handled here; the same document is never processed
twice, thanks to the hash-based dedup.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from scraper.database.models import Document, Equipment, EquipmentAssignment, PriceHistory, Variant
from scraper.normalization.equipment_alias import EquipmentNormalizer
from scraper.parsers.base import ExtractedVariant


class DocumentRepository:
    """Access to the `document` table."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, document_id: int) -> Document | None:
        """Args:
            document_id: Primary key of the `document` row to fetch.

        Returns:
            The matching `Document`, or `None` if `document_id` doesn't exist.
        """
        return self._session.get(Document, document_id)


class EquipmentRepository:
    """Get-or-create for canonical equipment (`Equipment`) — the raw name
    from the parser is normalized via `EquipmentNormalizer` before being
    stored, so the same piece of equipment across brands/documents maps
    to a single row (see architecture doc, Data Normalization section)."""

    def __init__(self, session: Session, normalizer: EquipmentNormalizer | None = None) -> None:
        self._session = session
        self._normalizer = normalizer or EquipmentNormalizer()

    def get_or_create(self, raw_name: str) -> Equipment:
        """Args:
            raw_name: Equipment name exactly as it appeared in the source
                PDF, before normalization.

        Returns:
            The existing `Equipment` row for `raw_name`'s canonical form
            (see `EquipmentNormalizer.normalize`), or a newly created one.
        """
        canonical_name = self._normalizer.normalize(raw_name)
        existing = self._session.query(Equipment).filter_by(canonical_name=canonical_name).first()
        if existing:
            return existing

        equipment = Equipment(canonical_name=canonical_name)
        self._session.add(equipment)
        self._session.flush()  # need equipment.id for EquipmentAssignment
        return equipment


class VariantRepository:
    """Storing and querying variants/prices/equipment derived from parser output."""

    def __init__(self, session: Session, equipment_repository: EquipmentRepository | None = None) -> None:
        self._session = session
        self._equipment = equipment_repository or EquipmentRepository(session)

    def save(
        self,
        document: Document,
        brand: str,
        variants: list[ExtractedVariant],
    ) -> list[Variant]:
        """Stores each ExtractedVariant as a Variant, (if it has a price) as
        the first record in PriceHistory with `valid_from` = the price
        list's effective date, and (if any) its equipment as EquipmentAssignment.

        Args:
            document: The already-persisted `Document` these variants
                were extracted from (used for `document_id` FKs and to
                derive `valid_from`).
            brand: Brand key to stamp onto every `Variant` (denormalized
                here rather than joined through `document` - see
                `Variant`'s own docstring in database/models.py).
            variants: Parser output to persist, one row per variant.

        Returns:
            The persisted `Variant` rows, in the same order as `variants`.
        """
        valid_from = document.release_date or document.downloaded_at.date()

        saved: list[Variant] = []
        for extracted in variants:
            variant = Variant(
                document_id=document.id,
                brand=brand,
                powertrain=extracted.powertrain,
                model=extracted.model,
                trim=extracted.trim,
                variant_name=extracted.variant_name,
                source_page=extracted.source_page,
                raw_text=extracted.raw_text,
            )
            self._session.add(variant)
            self._session.flush()  # need variant.id for PriceHistory/EquipmentAssignment

            if extracted.price is not None:
                self._session.add(
                    PriceHistory(
                        variant_id=variant.id,
                        document_id=document.id,
                        price=extracted.price,
                        currency=extracted.currency,
                        valid_from=valid_from,
                    )
                )

            self._add_equipment(variant, extracted)
            saved.append(variant)

        self._session.commit()
        return saved

    def _add_equipment(self, variant: Variant, extracted: ExtractedVariant) -> None:
        """Adds one `EquipmentAssignment` per item in `extracted.equipment`
        to `variant` (not committed)."""
        for raw_name, availability in extracted.equipment.items():
            equipment = self._equipment.get_or_create(raw_name)
            # `equipment_surcharge` is one flat dict per price list, so an
            # item that's paid on one trim but standard on another (Elroq's
            # heat pump) has a price there - a standard item never does.
            surcharge = None if availability == "STANDARD" else extracted.equipment_surcharge.get(raw_name)
            self._session.add(
                EquipmentAssignment(
                    variant_id=variant.id,
                    equipment_id=equipment.id,
                    availability=availability,
                    surcharge_amount=surcharge,
                    currency="CZK" if surcharge is not None else None,
                )
            )

    def replace_equipment(self, variant: Variant, extracted: ExtractedVariant) -> None:
        """Swaps `variant`'s equipment for `extracted`'s - for re-parsing an
        already-stored document after a parser improvement (see
        `scraper/reparse_equipment.py`). The variant and its price history
        are left alone. Not committed.

        Args:
            variant: The stored variant to update.
            extracted: Fresh parser output for the same variant.
        """
        self._session.query(EquipmentAssignment).filter(EquipmentAssignment.variant_id == variant.id).delete()
        self._add_equipment(variant, extracted)

    def list_for_document(self, document_id: int) -> list[Variant]:
        """Args:
            document_id: `document` row to list variants for.

        Returns:
            Every `Variant` stored for `document_id`, unordered.
        """
        return self._session.query(Variant).filter_by(document_id=document_id).all()

    def list_prices(self, variant_id: int) -> list[PriceHistory]:
        """Args:
            variant_id: `variant` row to list price history for.

        Returns:
            Every `PriceHistory` row stored for `variant_id`, unordered.
        """
        return self._session.query(PriceHistory).filter_by(variant_id=variant_id).all()

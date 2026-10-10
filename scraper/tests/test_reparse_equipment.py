"""reparse_equipment against the real Elroq fixture and an in-memory DB: a
variant stored with no equipment (as the old EV parser left it) gets the
parser's current equipment; its price history is not touched."""

from datetime import date, datetime
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from scraper.database.models import Base, Document, Equipment, EquipmentAssignment, PriceHistory, Variant
from scraper.reparse_equipment import reparse_document

ELROQ = Path(__file__).parent / "fixtures" / "skoda_elroq_cenik.pdf"


def _session_with_bare_elroq() -> tuple[Session, Variant, Variant]:
    session = Session(create_engine("sqlite://"))
    Base.metadata.create_all(session.get_bind())
    document = Document(
        source_brand="skoda",
        document_url="https://example.invalid/elroq",
        sha256_hash="0" * 64,
        file_path=str(ELROQ),
        release_date=date(2026, 6, 30),
        downloaded_at=datetime(2026, 7, 1),
    )
    session.add(document)
    session.flush()
    matched = Variant(
        document_id=document.id,
        brand="skoda",
        powertrain="EV",
        model="Elroq",
        trim="Selection",
        variant_name="Elroq 60 140 kW 61 kWh Selection",
        source_page=3,
        raw_text="",
    )
    unmatched = Variant(
        document_id=document.id,
        brand="skoda",
        powertrain="EV",
        model="Elroq",
        trim="Selection",
        variant_name="Elroq that no longer exists",
        source_page=3,
        raw_text="",
    )
    session.add_all([matched, unmatched])
    session.flush()
    session.add(
        PriceHistory(
            variant_id=matched.id, document_id=document.id, price=948000, currency="CZK", valid_from=date(2026, 6, 30)
        )
    )
    session.commit()
    return session, matched, unmatched


def _equipment(session: Session, variant: Variant) -> dict[str, str]:
    rows = (
        session.query(Equipment.canonical_name, EquipmentAssignment.availability)
        .join(Equipment, Equipment.id == EquipmentAssignment.equipment_id)
        .filter(EquipmentAssignment.variant_id == variant.id)
        .all()
    )
    return dict(rows)


def test_fills_equipment_and_keeps_prices() -> None:
    session, matched, unmatched = _session_with_bare_elroq()
    document = session.get(Document, matched.document_id)

    counts = reparse_document(session, document)

    assert counts == {"updated": 1, "unmatched": 1}
    equipment = _equipment(session, matched)
    assert "STANDARD" in equipment.values()
    assert "OPTIONAL" in equipment.values()
    assert _equipment(session, unmatched) == {}
    assert [p.price for p in session.query(PriceHistory).all()] == [948000]


def test_standard_items_never_carry_a_surcharge() -> None:
    session, matched, _ = _session_with_bare_elroq()
    reparse_document(session, session.get(Document, matched.document_id))

    standard_with_price = (
        session.query(EquipmentAssignment)
        .filter(EquipmentAssignment.availability == "STANDARD", EquipmentAssignment.surcharge_amount.is_not(None))
        .count()
    )
    assert standard_with_price == 0


def test_running_twice_does_not_duplicate() -> None:
    session, matched, _ = _session_with_bare_elroq()
    document = session.get(Document, matched.document_id)

    reparse_document(session, document)
    first = session.query(EquipmentAssignment).count()
    reparse_document(session, document)

    assert session.query(EquipmentAssignment).count() == first


def test_dry_run_writes_nothing() -> None:
    session, matched, _ = _session_with_bare_elroq()
    document = session.get(Document, matched.document_id)

    counts = reparse_document(session, document, dry_run=True)

    assert counts["updated"] == 1
    assert session.query(EquipmentAssignment).count() == 0

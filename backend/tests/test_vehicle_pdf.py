"""PDF export of one vehicle (app/ui/vehicle_pdf.py), against the seeded
demo catalog. The text is read back with pdfplumber (already a scraper
dependency) to check what a reader actually sees, not just that bytes came out.
"""

import io
from datetime import date

import pdfplumber
import pytest

from app.services import catalog
from app.ui import vehicle_pdf
from app.ui.money import format_money
from tests.conftest import SeededData


def _text(content: bytes) -> str:
    with pdfplumber.open(io.BytesIO(content)) as pdf:
        return "\n".join(page.extract_text() or "" for page in pdf.pages)


def test_pdf_contains_vehicle_detail(seeded_session: SeededData) -> None:
    detail = catalog.get_vehicle_detail(seeded_session.session, seeded_session.config_rline_awd_id)
    assert detail is not None

    content = vehicle_pdf.build_vehicle_pdf(detail, today=date(2026, 9, 25))

    assert content.startswith(b"%PDF")
    text = _text(content)
    assert f"{detail.brand} {detail.model} {detail.trim}" in text
    # pdfplumber reads the no-break spaces in money back as plain spaces.
    assert format_money(detail.price).replace(" ", " ") in text
    assert "Vytvořeno 25. 09. 2026" in text
    assert "MOTOR A POHON" in text
    assert detail.standard_equipment[0] in text
    assert detail.optional_equipment[0].name in text
    assert "Strana 1/" in text


def test_pdf_without_unicode_font_strips_diacritics(
    seeded_session: SeededData, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(vehicle_pdf, "_find_fonts", lambda: None)
    detail = catalog.get_vehicle_detail(seeded_session.session, seeded_session.config_prime_2wd_id)
    assert detail is not None

    text = _text(vehicle_pdf.build_vehicle_pdf(detail))

    assert "Vytvoreno" in text
    assert detail.brand in text


def test_pdf_filename_is_ascii_slug(seeded_session: SeededData) -> None:
    detail = catalog.get_vehicle_detail(seeded_session.session, seeded_session.config_rline_awd_id)
    assert detail is not None
    detail = detail.model_copy(update={"brand": "Škoda", "model": "Kodiaq", "trim": "Style 2.0 TDI 4×4"})

    assert vehicle_pdf.pdf_filename(detail) == "skoda-kodiaq-style-2-0-tdi-4-4.pdf"

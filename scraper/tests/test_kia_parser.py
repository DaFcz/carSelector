"""Tests for KiaParser on real price lists (downloaded 2026-08-13 from
kia.com, effective from 2026-08-01 — see scraper/tests/fixtures/kia_*.pdf).
Prices are transcribed by hand from the PDF text (pdfplumber.extract_text
on page 2 of each), so it can always be verified that the extraction
matches the source — same discipline as test_parsers.py (Škoda) and
test_volkswagen_parser.py.

Sportage's ICE and HEV/PHEV variants are two separate documents (see
parsers/kia.py and monitors/discovery/kia.py), hence two fixtures and two
sets of Sportage tests below."""

from pathlib import Path

from scraper.parsers.kia import KiaParser

FIXTURES = Path(__file__).parent / "fixtures"
NIRO = FIXTURES / "kia_niro_cenik.pdf"
CEED_SW = FIXTURES / "kia_ceed_sw_cenik.pdf"
SPORTAGE_ICE = FIXTURES / "kia_sportage_ice_cenik.pdf"
SPORTAGE_HEV_PHEV = FIXTURES / "kia_sportage_hev_phev_cenik.pdf"


def _variant(variants, trim: str, engine_fragment: str):
    return next(v for v in variants if v.trim == trim and engine_fragment in v.raw_text)


def test_kia_parser_extracts_niro_variants() -> None:
    # 3 trims (Comfort/Style/Premium), each with a single 1,6 GDI HEV engine
    variants = KiaParser().parse(NIRO)
    assert len(variants) == 3
    assert all(v.model == "Niro" for v in variants)
    assert all(v.powertrain == "HEV" for v in variants)

    assert _variant(variants, "Comfort", "1,6 GDI HEV").price == 814_980.0
    assert _variant(variants, "Style", "1,6 GDI HEV").price == 869_980.0
    assert _variant(variants, "Premium", "1,6 GDI HEV").price == 979_980.0


def test_kia_parser_extracts_ceed_sw_variants() -> None:
    # SPIN and TOP trims, 3 engine options each, all ICE
    variants = KiaParser().parse(CEED_SW)
    assert len(variants) == 6
    assert all(v.model == "Ceed SW" for v in variants)
    assert all(v.powertrain == "ICE" for v in variants)

    assert _variant(variants, "SPIN", "1.0 T-GDI").price == 514_980.0
    assert _variant(variants, "SPIN", "7DCT").price == 609_980.0
    assert _variant(variants, "TOP", "1.0 T-GDI").price == 559_980.0
    assert _variant(variants, "TOP", "7DCT").price == 654_980.0


def test_kia_parser_extracts_sportage_ice_variants() -> None:
    # Comfort(1) + Exclusive(5, incl. 2 MHEV) + BLACK EDITION(3) + TOP(5, incl. 2 MHEV) + GT-Line(3, incl. 1 MHEV)
    variants = KiaParser().parse(SPORTAGE_ICE)
    assert len(variants) == 17
    assert all(v.model == "Sportage" for v in variants)

    assert _variant(variants, "Comfort", "6MT").price == 729_980.0
    assert _variant(variants, "GT-Line", "4x4 7DCT").price == 1_034_980.0

    # MHEV (mild hybrid diesel) rows are correctly distinguished from plain ICE
    mhev = _variant(variants, "TOP", "CRDi SCR 4x2 MHEV 7DCT")
    assert mhev.powertrain == "MHEV"
    assert mhev.price == 1_009_980.0
    assert _variant(variants, "Comfort", "6MT").powertrain == "ICE"


def test_kia_parser_extracts_sportage_hev_phev_variants() -> None:
    # Comfort(2) + Exclusive(4) + BLACK EDITION(4) + TOP(4) + GT-Line(4), mixing HEV and PHEV rows
    variants = KiaParser().parse(SPORTAGE_HEV_PHEV)
    assert len(variants) == 18
    assert all(v.model == "Sportage" for v in variants)

    hev = _variant(variants, "Comfort", "HEV 6AT")
    assert hev.powertrain == "HEV"
    assert hev.price == 904_980.0

    # price above 999,999 Kč, split across multiple words in the PDF ("1" "079" "980")
    phev = _variant(variants, "Comfort", "PHEV 6AT")
    assert phev.powertrain == "PHEV"
    assert phev.price == 1_079_980.0

    assert _variant(variants, "GT-Line", "4x4 PHEV").price == 1_314_980.0


def test_kia_parser_raw_text_traceable_to_source() -> None:
    variants = KiaParser().parse(NIRO)
    variant = _variant(variants, "Comfort", "1,6 GDI HEV")
    assert "814 980" in variant.raw_text
    assert variant.source_page == 2

"""Test for VolkswagenParser on a real Golf price list (downloaded
2026-07-19 from volkswagen.cz, effective from 2026-04-01 — see
scraper/tests/fixtures/vw_golf_cenik.pdf). The prices in the test are
transcribed by hand from the PDF text (pdfplumber.extract_text on p. 2),
so it can always be verified that the extraction matches the source —
same discipline as test_parsers.py (Škoda).

16 = 1 variant of the "Golf" trim (no name of its own) + 6 "Life" + 5
"Style" + 4 "R-Line"."""

from pathlib import Path

from scraper.parsers.volkswagen import VolkswagenParser

FIXTURE = Path(__file__).parent / "fixtures" / "vw_golf_cenik.pdf"


def _variant(variants, trim: str, engine_fragment: str):
    return next(v for v in variants if v.trim == trim and engine_fragment in v.variant_name)


def test_volkswagen_parser_extracts_expected_variant_count() -> None:
    variants = VolkswagenParser().parse(FIXTURE)
    assert len(variants) == 16
    assert all(v.model == "Golf" for v in variants)


def test_volkswagen_parser_prices_match_source_pdf() -> None:
    variants = VolkswagenParser().parse(FIXTURE)

    # base trim (no name of its own, same as the model) — "1,5 TSI / 85 kW ... 677 900 Kč"
    assert _variant(variants, "Golf", "1,5 TSI").price == 677_900.0

    # Life trim — "2,0 TDI / 85 kW ... 770 900 Kč" and "1,5 TSI PHEV / 110 kW ... 981 900 Kč"
    assert _variant(variants, "Life", "2,0 TDI").price == 770_900.0
    assert _variant(variants, "Life", "1,5 TSI PHEV").price == 981_900.0

    # Style trim — price above 999,999 Kč ("1 057 900 Kč")
    style_phev = _variant(variants, "Style", "1,5 TSI PHEV")
    assert style_phev.price == 1_057_900.0

    # R-Line trim, the only variant with "Všech kol" ("all-wheel") drivetrain (2,0 TSI 4MOTION)
    r_line_4motion = _variant(variants, "R-Line", "4MOTION")
    assert r_line_4motion.price == 972_900.0


def test_volkswagen_parser_classifies_powertrain_per_row() -> None:
    variants = VolkswagenParser().parse(FIXTURE)

    assert _variant(variants, "Golf", "1,5 TSI").powertrain == "ICE"
    assert _variant(variants, "Life", "1,5 eTSI mHEV / 85 kW").powertrain == "MHEV"
    assert _variant(variants, "Life", "1,5 TSI PHEV").powertrain == "PHEV"


def test_volkswagen_parser_raw_text_traceable_to_source() -> None:
    variants = VolkswagenParser().parse(FIXTURE)
    variant = _variant(variants, "Golf", "1,5 TSI")
    assert "677 900" in variant.raw_text
    assert variant.source_page == 2

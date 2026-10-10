"""Test for SkodaParser on a real Octavia price list (downloaded
2026-07-10, effective from 2026-07-09 — see
scraper/tests/fixtures/skoda_octavia_cenik.pdf). The prices in the test
are transcribed by hand from the PDF, so it can always be verified that
the extraction matches the source.

70 = 54 variants from the main table (Essence/Selection/.../RS) + 16
variants from the "Akční modely Classic a Dynamic" ("Promotional models
Classic and Dynamic") table on pages 11-12 — the Octavia has this extra
table, and an earlier version of the parser (with a fixed header
x-coordinate tuned only for the main table) missed it. The new parser
looks up the header by the text "Motor"/"Pohon", not by a fixed
position, so it finds both tables, and any number of others on other pages."""

from pathlib import Path

from scraper.parsers.skoda_ice import SkodaIceParser

FIXTURE = Path(__file__).parent / "fixtures" / "skoda_octavia_cenik.pdf"


def _variant(variants, trim: str, motor_fragment: str):
    return next(v for v in variants if v.trim == trim and motor_fragment in v.variant_name)


def test_skoda_ice_parser_extracts_expected_variant_count() -> None:
    variants = SkodaIceParser().parse(FIXTURE)
    assert len(variants) == 70
    assert all(v.powertrain == "ICE" for v in variants)


def test_skoda_ice_parser_prices_match_source_pdf() -> None:
    variants = SkodaIceParser().parse(FIXTURE)

    # Liftback, 1,5 TSI/85 kW manual — Essence/Selection/Top Selection
    assert _variant(variants, "Essence", "1,5 TSI/85 kW").price == 609_900.0
    assert _variant(variants, "Selection", "1,5 TSI/85 kW").price == 669_900.0
    assert _variant(variants, "Top Selection", "1,5 TSI/85 kW").price == 739_900.0

    # Liftback, 2,0 TSI/195 kW — only offered as RS (other trims "–")
    rs_variant = _variant(variants, "RS", "2,0 TSI/195 kW")
    assert rs_variant.price == 1_069_900.0
    assert rs_variant.model == "Octavia"

    # price above 999,999 Kč split across multiple words in the PDF ("1" "009" "900")
    assert _variant(variants, "Top Selection", "2,0 TSI/150 kW").price == 1_009_900.0

    # p. 11: second price table on the page ("Akční modely Classic a
    # Dynamic"), different trim names and a different header x-coordinate
    # than the main table — verifies that the header isn't looked up by a fixed position
    assert _variant(variants, "Classic", "1,5 TSI/110 kW").price == 719_900.0
    assert _variant(variants, "Dynamic", "1,5 TSI/110 kW").price == 833_900.0


def test_skoda_ice_parser_finds_second_price_table_on_same_page() -> None:
    variants = SkodaIceParser().parse(FIXTURE)
    classic_dynamic = [v for v in variants if v.trim in ("Classic", "Dynamic")]
    assert len(classic_dynamic) == 16
    assert {v.source_page for v in classic_dynamic} == {11, 12}


def test_skoda_ice_parser_raw_text_traceable_to_source() -> None:
    variants = SkodaIceParser().parse(FIXTURE)
    variant = _variant(variants, "Essence", "1,5 TSI/85 kW")
    assert "609 900" in variant.raw_text
    assert variant.source_page == 3

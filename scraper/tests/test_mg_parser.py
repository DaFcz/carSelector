"""Tests for MgParser on all seven real per-model price lists (downloaded
2026-09-13 from mgmotor-czech.cz, effective June-September 2026 depending
on model - see scraper/tests/fixtures/mg_*.pdf). Prices and row counts
are transcribed by hand from `page.extract_text()` output for every
fixture, not just spot-checked - same discipline as test_opel_parser.py."""

from pathlib import Path

from scraper.parsers.mg import MgParser

FIXTURES = Path(__file__).parent / "fixtures"
MG3 = FIXTURES / "mg_mg3_cenik.pdf"
MGS9_PHEV = FIXTURES / "mg_mgs9phev_cenik.pdf"
ZS = FIXTURES / "mg_zs_cenik.pdf"
HS = FIXTURES / "mg_hs_cenik.pdf"
MG4_EV = FIXTURES / "mg_mg4ev_cenik.pdf"
MGS5_EV = FIXTURES / "mg_mgs5ev_cenik.pdf"
CYBERSTER = FIXTURES / "mg_cyberster_cenik.pdf"


def _variant(variants, trim: str, engine_fragment: str):
    return next(v for v in variants if v.trim == trim and engine_fragment in v.variant_name)


def test_mg_parser_extracts_mg3_variants_and_skips_stock_only_table() -> None:
    # The document has TWO price tables (a "skladové vozy" stock-only one
    # first, then the regular one) - only the regular one (5 trims, one
    # engine each) should be read; reading both would double every row.
    variants = MgParser().parse(MG3)
    assert len(variants) == 5
    assert all(v.model == "3" for v in variants)
    assert all(v.currency == "CZK" for v in variants)

    base = _variant(variants, "Excite", "Zážehový")
    assert base.price == 429_990.0
    assert base.powertrain == "ICE"

    hev = _variant(variants, "Exclusive", "Hybrid+")
    assert hev.powertrain == "HEV"
    assert hev.price == 569_990.0


def test_mg_parser_extracts_mgs9_phev_variants() -> None:
    variants = MgParser().parse(MGS9_PHEV)
    assert len(variants) == 2
    assert all(v.model == "S9 PHEV" for v in variants)
    assert all(v.powertrain == "PHEV" for v in variants)


def test_mg_parser_extracts_zs_variants() -> None:
    variants = MgParser().parse(ZS)
    assert len(variants) == 5
    assert all(v.model == "ZS" for v in variants)
    assert {v.trim for v in variants} == {"Excite", "Elegance", "Essential", "Emotion", "Exclusive"}


def test_mg_parser_extracts_hs_variants_with_vertically_merged_trim_cell() -> None:
    # A regression test for the bug this parser's own docstring describes:
    # HS's own first trim heading ("Emotion") is centered against all 4
    # of its rows and lands BETWEEN the 2nd and 3rd in reading order - a
    # naive "carry the last-seen heading forward" reader would misplace
    # rows onto the wrong trim. Also: the "SUMMER EDITION" single-row
    # stock promo page (no "CENÍK MG HS" title) and the regular table's
    # own footnote line (whose leading "*" sits left of the trim column,
    # the same as a real trim word would) must not produce spurious rows
    # or corrupt trim assignment for the row after them.
    variants = MgParser().parse(HS)
    assert len(variants) == 8
    assert all(v.model == "HS" for v in variants)
    assert {v.trim for v in variants} == {"Emotion", "Exclusive"}
    assert sum(1 for v in variants if v.trim == "Emotion") == 4
    assert sum(1 for v in variants if v.trim == "Exclusive") == 4

    last_exclusive_phev = _variant(variants, "Exclusive", "PHEV")
    assert last_exclusive_phev.price == 999_990.0
    assert last_exclusive_phev.powertrain == "PHEV"


def test_mg_parser_extracts_mg4_ev_urban_variants() -> None:
    variants = MgParser().parse(MG4_EV)
    assert len(variants) == 3
    assert all(v.model == "4 EV Urban" for v in variants)
    assert all(v.powertrain == "EV" for v in variants)

    comfort_54kwh = _variant(variants, "Comfort", "54 kWh")
    assert comfort_54kwh.price == 649_990.0


def test_mg_parser_extracts_mgs5_ev_variants_with_rwd() -> None:
    variants = MgParser().parse(MGS5_EV)
    assert len(variants) == 3
    assert all(v.model == "S5 EV" for v in variants)
    assert all("Zadní" in v.variant_name for v in variants)


def test_mg_parser_extracts_cyberster_variants_with_awd() -> None:
    # A regression test for a bug where the POHON value "4×4" (immediately
    # before the price, with only a space between them) let its own
    # trailing "4" bleed into the price digits, corrupting 1 759 000 into
    # 41 759 000.
    variants = MgParser().parse(CYBERSTER)
    assert len(variants) == 2
    assert all(v.model == "Cyberster" for v in variants)
    assert all(v.powertrain == "EV" for v in variants)

    trophy = _variant(variants, "Trophy", "250 kW")
    gt = _variant(variants, "GT", "375 kW")
    assert trophy.price == 1_639_000.0
    assert gt.price == 1_759_000.0
    assert "4×4" in gt.variant_name


def test_mg_parser_raw_text_traceable_to_source() -> None:
    variants = MgParser().parse(MG3)
    variant = _variant(variants, "Excite", "Zážehový")
    assert "429" in variant.raw_text
    assert "990" in variant.raw_text
    assert variant.source_page == 3

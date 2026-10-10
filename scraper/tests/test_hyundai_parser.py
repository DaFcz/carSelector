"""Tests for HyundaiParser on real price lists (downloaded 2026-08-28 from
dmassets.hyundai.com, model year 2027, effective from 2026-08-17 — see
scraper/tests/fixtures/hyundai_*.pdf). Prices are transcribed by hand from
the PDF text, so it can always be verified that the extraction matches the
source — same discipline as test_kia_parser.py.

Tucson's ICE/MHEV and HEV/PHEV variants are two separate documents (see
parsers/hyundai.py and monitors/discovery/hyundai.py), hence two fixtures
and two sets of Tucson tests below."""

from pathlib import Path

from scraper.parsers.hyundai import HyundaiParser

FIXTURES = Path(__file__).parent / "fixtures"
I20 = FIXTURES / "hyundai_i20_cenik.pdf"
I30 = FIXTURES / "hyundai_i30_cenik.pdf"
KONA = FIXTURES / "hyundai_kona_cenik.pdf"
TUCSON = FIXTURES / "hyundai_tucson_cenik.pdf"
TUCSON_HEV_PHEV = FIXTURES / "hyundai_tucson_hev_phev_cenik.pdf"
SANTA_FE = FIXTURES / "hyundai_santa_fe_cenik.pdf"


def _variant(variants, trim: str, engine_fragment: str):
    return next(v for v in variants if v.trim == trim and engine_fragment in v.raw_text)


def test_hyundai_parser_extracts_i20_variants() -> None:
    # START(1) + COMFORT(2) + SMART(2) + STYLE(2), all ICE, no 7-digit prices
    variants = HyundaiParser().parse(I20)
    assert len(variants) == 7
    assert all(v.model == "i20" for v in variants)
    assert all(v.powertrain == "ICE" for v in variants)

    assert _variant(variants, "START", "6st. manuální").price == 460_990.0
    assert _variant(variants, "STYLE", "7st. DCT1").price == 630_990.0


def test_hyundai_parser_extracts_i30_variants() -> None:
    # COMFORT(1) + SMART(2) + STYLE(2) + PREMIUM(1) + N LINE PREMIUM(1), all ICE
    variants = HyundaiParser().parse(I30)
    assert len(variants) == 7
    assert all(v.model == "i30" for v in variants)
    assert all(v.powertrain == "ICE" for v in variants)

    assert _variant(variants, "COMFORT", "1,0 T-GDI").price == 519_990.0
    assert _variant(variants, "N LINE PREMIUM", "1,6 T-GDI").price == 789_990.0


def test_hyundai_parser_extracts_kona_variants() -> None:
    # COMFORT(1) + COMFORT CLUB(3) + SMART(5) + STYLE(5) + N LINE(5) + N LINE STYLE(5), all ICE
    variants = HyundaiParser().parse(KONA)
    assert len(variants) == 24
    assert all(v.model == "Kona" for v in variants)
    assert all(v.powertrain == "ICE" for v in variants)

    assert _variant(variants, "COMFORT", "1,0 T-GDI").price == 629_990.0
    assert _variant(variants, "N LINE STYLE", "4×4").price == 899_990.0


def test_hyundai_parser_extracts_tucson_ice_variants() -> None:
    # COMFORT(1) + SMART(2) + PREMIUM LUXURY(6, incl. 3 MHEV) + N LINE(6, incl. 3 MHEV) + N LINE PREMIUM(6, incl. 3 MHEV)
    variants = HyundaiParser().parse(TUCSON)
    assert len(variants) == 21
    assert all(v.model == "Tucson" for v in variants)

    assert _variant(variants, "COMFORT", "6st. manuální").price == 749_990.0
    # price above 999,999 Kč, split across multiple words in the PDF ("1" "119" "990")
    assert _variant(variants, "PREMIUM LUXURY", "4×4 132/180 7st. DCT2").price == 1_119_990.0

    mhev = _variant(variants, "N LINE", "CRDi MHEV 48V1 4×2 100/136 6st. manuální")
    assert mhev.powertrain == "MHEV"
    assert mhev.price == 969_990.0
    assert _variant(variants, "COMFORT", "6st. manuální").powertrain == "ICE"


def test_hyundai_parser_extracts_tucson_hev_phev_variants() -> None:
    # SMART(2) + PREMIUM LUXURY(4) + N LINE(4) + N LINE PREMIUM(4), mixing HEV and PHEV rows
    variants = HyundaiParser().parse(TUCSON_HEV_PHEV)
    assert len(variants) == 14
    assert all(v.model == "Tucson" for v in variants)

    hev = _variant(variants, "SMART", "HEV* 1,6 T-GDI HEV")
    assert hev.powertrain == "HEV"
    assert hev.price == 959_990.0

    phev = _variant(variants, "SMART", "PHEV 1,6 T-GDI PHEV")
    assert phev.powertrain == "PHEV"
    assert phev.price == 1_069_990.0

    assert _variant(variants, "N LINE PREMIUM", "PHEV 1,6 T-GDI PHEV 4×4").price == 1_339_990.0


def test_hyundai_parser_extracts_santa_fe_variants_across_two_pages() -> None:
    # HEV table on page 1: COMFORT(2) + SMART(2) + STYLE(2) + CALLIGRAPHY(1);
    # PHEV table on page 8: COMFORT(1) + STYLE(1) + CALLIGRAPHY(1)
    variants = HyundaiParser().parse(SANTA_FE)
    assert len(variants) == 10
    assert all(v.model == "Santa Fe" for v in variants)

    hev = _variant(variants, "CALLIGRAPHY", "Hybrid 1,6 T-GDI")
    assert hev.powertrain == "HEV"
    assert hev.price == 1_639_990.0
    assert hev.source_page == 1

    # price above 999,999 Kč in all three columns ("1 469 990" / "1 369 990" / "1 032 638")
    phev = _variant(variants, "COMFORT", "Plug-in hybrid")
    assert phev.powertrain == "PHEV"
    assert phev.price == 1_469_990.0
    assert phev.source_page == 8


def test_hyundai_parser_raw_text_traceable_to_source() -> None:
    variants = HyundaiParser().parse(I20)
    variant = _variant(variants, "START", "6st. manuální")
    assert "460 990" in variant.raw_text
    assert variant.source_page == 1

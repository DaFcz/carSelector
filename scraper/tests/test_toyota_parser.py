"""Tests for ToyotaParser on real price lists (downloaded 2026-08-13 from
pdf.sites.toyota.cz — see scraper/tests/fixtures/toyota_*.pdf). Prices
are transcribed by hand from the PDF text (pdfplumber.extract_words on
the "SEZNAMTE SE S CENAMI" price-table page of each), so it can always be
verified that the extraction matches the source — same discipline as
test_parsers.py (Škoda) and test_kia_parser.py.

Corolla's three body styles (Sedan/Hatchback/Touring Sports) are three
separate documents (see parsers/toyota.py and monitors/discovery/toyota.py),
hence three fixtures and three sets of Corolla tests below."""

from pathlib import Path

from scraper.parsers.toyota import ToyotaParser

FIXTURES = Path(__file__).parent / "fixtures"
YARIS = FIXTURES / "toyota_yaris_cenik.pdf"
YARIS_CROSS = FIXTURES / "toyota_yaris_cross_cenik.pdf"
COROLLA_SEDAN = FIXTURES / "toyota_corolla_sedan_cenik.pdf"
COROLLA_HATCHBACK = FIXTURES / "toyota_corolla_hatchback_cenik.pdf"
COROLLA_TS = FIXTURES / "toyota_corolla_ts_cenik.pdf"
CHR = FIXTURES / "toyota_chr_cenik.pdf"
RAV4 = FIXTURES / "toyota_rav4_cenik.pdf"


def _variant(variants, trim: str, engine_fragment: str):
    return next(v for v in variants if v.trim == trim and engine_fragment in v.raw_text)


def test_toyota_parser_extracts_yaris_variants() -> None:
    # 1.5 Hybrid 115: Active/Comfort/Style; 1.5 Hybrid 130: Executive/GR SPORT (dashes elsewhere)
    variants = ToyotaParser().parse(YARIS)
    assert len(variants) == 5
    assert all(v.model == "Yaris" for v in variants)
    assert all(v.powertrain == "HEV" for v in variants)

    assert _variant(variants, "Active", "Hybrid 115").price == 559_000.0
    assert _variant(variants, "Style", "Hybrid 115").price == 634_000.0
    assert _variant(variants, "Executive", "Hybrid 130").price == 689_000.0
    assert _variant(variants, "GR SPORT", "Hybrid 130").price == 704_000.0


def test_toyota_parser_extracts_yaris_cross_variants() -> None:
    # FWD 115 (Active/Comfort only), FWD 130 (all 5 trims), AWD-i 130 (Comfort/Style/Executive)
    variants = ToyotaParser().parse(YARIS_CROSS)
    assert len(variants) == 9
    assert all(v.model == "Yaris Cross" for v in variants)

    assert _variant(variants, "Active", "FWD").price == 599_000.0
    assert _variant(variants, "GR SPORT", "FWD").price == 784_000.0
    awd_style = _variant(variants, "Style", "AWD-i")
    assert awd_style.price == 749_000.0


def test_toyota_parser_extracts_corolla_sedan_variants() -> None:
    # single 1.8 Hybrid engine, all 5 trims populated
    variants = ToyotaParser().parse(COROLLA_SEDAN)
    assert len(variants) == 5
    assert all(v.model == "Corolla Sedan" for v in variants)

    assert _variant(variants, "Active", "1.8 Hybrid").price == 723_900.0
    assert _variant(variants, "GR SPORT", "1.8 Hybrid").price == 911_900.0
    assert _variant(variants, "Executive", "1.8 Hybrid").price == 959_900.0


def test_toyota_parser_extracts_corolla_hatchback_variants() -> None:
    # 1.8 Hybrid: Comfort/Style/GR SPORT/Executive; 2.0 Hybrid: Style/GR SPORT/Executive (no Comfort)
    variants = ToyotaParser().parse(COROLLA_HATCHBACK)
    assert len(variants) == 7
    assert all(v.model == "Corolla Hatchback" for v in variants)

    assert _variant(variants, "Comfort", "1.8 Hybrid").price == 747_900.0
    v20 = _variant(variants, "Executive", "2.0 Hybrid")
    assert v20.price == 1_029_900.0


def test_toyota_parser_extracts_corolla_touring_sports_variants() -> None:
    variants = ToyotaParser().parse(COROLLA_TS)
    assert len(variants) == 8
    assert all(v.model == "Corolla Touring Sports" for v in variants)

    assert _variant(variants, "Comfort", "1.8 Hybrid").price == 777_900.0
    assert _variant(variants, "Comfort", "2.0 Hybrid").price == 852_900.0
    assert _variant(variants, "Executive", "2.0 Hybrid").price == 1_059_900.0


def test_toyota_parser_extracts_chr_variants_with_comfort_plus_trim() -> None:
    # "Comfort" and "Comfort Plus" are two distinct trims (two header words merged, see parsers/toyota.py)
    variants = ToyotaParser().parse(CHR)
    assert len(variants) == 14
    assert all(v.model == "C-HR" for v in variants)

    plain_comfort = _variant(variants, "Comfort", "1.8 Hybrid")
    assert plain_comfort.price == 809_900.0
    assert plain_comfort.powertrain == "HEV"

    # PHEV row: plain "Comfort" isn't offered (only "Comfort Plus" is) — price above 999,999 Kč,
    # split across multiple words in the PDF ("1" "019" "900")
    comfort_plus = _variant(variants, "Comfort Plus", "Plug-in")
    assert comfort_plus.price == 979_900.0
    assert comfort_plus.powertrain == "PHEV"
    assert _variant(variants, "Style", "Plug-in").price == 1_019_900.0
    assert not any(v.trim == "Comfort" and "Plug-in" in v.raw_text for v in variants)


def test_toyota_parser_extracts_rav4_variants() -> None:
    # FWD Hybrid (Comfort/Style/Executive, no GR SPORT) + AWD Hybrid (all 4) +
    # FWD Plug-in (Comfort/Style/Executive) + AWD Plug-in (all 4)
    variants = ToyotaParser().parse(RAV4)
    assert len(variants) == 14
    assert all(v.model == "RAV4" for v in variants)

    fwd_hev = _variant(variants, "Comfort", "Hybrid (185")
    assert fwd_hev.price == 1_090_000.0
    assert fwd_hev.powertrain == "HEV"
    assert not any(v.trim == "GR SPORT" and "(185" in v.raw_text for v in variants)

    awd_hev_gr_sport = _variant(variants, "GR SPORT", "Hybrid (194")
    assert awd_hev_gr_sport.price == 1_410_000.0

    phev = _variant(variants, "Executive", "Plug-in Hybrid (309")
    assert phev.price == 1_550_000.0
    assert phev.powertrain == "PHEV"


def test_toyota_parser_raw_text_traceable_to_source() -> None:
    variants = ToyotaParser().parse(YARIS)
    variant = _variant(variants, "Active", "Hybrid 115")
    assert "559" in variant.raw_text
    assert variant.source_page == 4

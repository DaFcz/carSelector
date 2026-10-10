"""Tests for BmwParser on the real combined price list (downloaded
2026-08-29 from bmw.cz, effective 1 July 2026 — see scraper/tests/
fixtures/bmw_cenik.pdf). Prices are transcribed by hand from the PDF text,
so it can always be verified that the extraction matches the source —
same discipline as test_kia_parser.py.

The fixture covers BMW's entire current lineup (29 model sections across
6 pages) — these tests check a representative cross-section (combustion,
electric, plug-in hybrid, a section split across two pages, and a section
sharing its page with an M-performance chassis annotation) rather than
every row."""

from pathlib import Path

from scraper.parsers.bmw import BmwParser

FIXTURE = Path(__file__).parent / "fixtures" / "bmw_cenik.pdf"


def _variant(variants, model: str, trim: str):
    return next(v for v in variants if v.model == model and v.trim == trim)


def test_bmw_parser_extracts_entire_lineup() -> None:
    variants = BmwParser().parse(FIXTURE)
    assert len(variants) == 145
    assert len({v.model for v in variants}) == 29
    assert all(v.currency == "CZK" for v in variants)


def test_bmw_parser_extracts_ice_variants() -> None:
    variants = BmwParser().parse(FIXTURE)

    base = _variant(variants, "1 Series", "116")
    assert base.powertrain == "ICE"
    assert base.price == 794_300.0  # VAT-inclusive price, not the 656 446 Kč ex-VAT figure
    assert base.source_page == 2

    # price above 999,999 Kč, split across multiple words in the PDF ("2" "805" "400")
    m3_touring = _variant(variants, "3 Series Touring", "M3 Competition M xDrive")
    assert m3_touring.powertrain == "ICE"
    assert m3_touring.price == 2_805_400.0

    # same trim name, different body style/section -> different price
    m3_sedan = _variant(variants, "3 Series Sedan", "M3 Competition M xDrive")
    assert m3_sedan.price == 2_778_100.0
    assert m3_sedan.price != m3_touring.price


def test_bmw_parser_variant_name_survives_powertrain_signature_stripping() -> None:
    # scripts/import_scraper_data.py's powertrain_signature() dedups "the
    # same engine across trims" within one model by stripping `trim` out
    # of `variant_name` - since BMW's own `trim` (e.g. "320d") already IS
    # the row's entire distinguishing text, variant_name must carry real
    # extra content (here: displacement/power, plus an explicit "AWD"
    # marker for the handful of pairs that share an identical spec and
    # differ only by xDrive) so two different rows in the same model never
    # reduce to the same signature - see _parse_row's own comment on this.
    import sys as _sys

    _sys.path.insert(0, str(FIXTURE.parents[3]))  # repo root, for scripts/
    from scripts.import_scraper_data import powertrain_signature

    variants = [v for v in BmwParser().parse(FIXTURE) if v.model == "3 Series Sedan"]
    signatures = {powertrain_signature(v.variant_name, v.trim) for v in variants}
    assert len(signatures) == len(variants)


def test_bmw_parser_extracts_plugin_hybrid_variants() -> None:
    # PHEV rows are mixed into their combustion model's own section, not a separate one
    variants = [v for v in BmwParser().parse(FIXTURE) if v.model == "3 Series Sedan"]
    assert any(v.powertrain == "ICE" for v in variants)

    phev = _variant(variants, "3 Series Sedan", "330e")
    assert phev.powertrain == "PHEV"
    assert phev.price == 1_502_800.0

    phev_awd = _variant(variants, "3 Series Sedan", "330e xDrive")
    assert phev_awd.powertrain == "PHEV"
    assert phev_awd.price == 1_567_800.0


def test_bmw_parser_extracts_electric_variants() -> None:
    # "i5 Touring" is its own section, entirely separate from "5 Series Touring"
    variants = [v for v in BmwParser().parse(FIXTURE) if v.model == "i5 Touring"]
    assert len(variants) == 3
    assert all(v.powertrain == "EV" for v in variants)

    base = _variant(variants, "i5 Touring", "i5 eDrive40")
    assert base.price == 1_799_200.0

    top = _variant(variants, "i5 Touring", "i5 M60 xDrive")
    assert top.price == 2_606_500.0


def test_bmw_parser_merges_section_continued_across_pages() -> None:
    # "BMW řady 3 Touring (G21) / M3 Touring (G81)" starts on one page and
    # repeats as "... - pokračování" on the next - both must map to the
    # same "3 Series Touring" model, not two different ones.
    variants = [v for v in BmwParser().parse(FIXTURE) if v.model == "3 Series Touring"]
    pages = {v.source_page for v in variants}
    assert len(pages) > 1
    assert len(variants) == 12


def test_bmw_parser_raw_text_traceable_to_source() -> None:
    variants = BmwParser().parse(FIXTURE)
    variant = _variant(variants, "1 Series", "116")
    assert "656 446" in variant.raw_text  # ex-VAT price, kept for verification even though not stored as `price`
    assert "794 300" in variant.raw_text  # VAT-inclusive price == variant.price
    assert variant.source_page == 2

"""Tests for MazdaParser on real price lists (downloaded 2026-08-29 from
media-assets.mazda.eu, effective 2026-07/2026-08 — see scraper/tests/
fixtures/mazda_*.pdf). Prices are transcribed by hand from the PDF's own
clean-rendered price tables (cross-checked against a rendered page image,
not just extracted text — see parsers/mazda.py's module docstring for why
naive extraction can't be trusted at face value here), same discipline as
test_kia_parser.py.

Mazda3 is the only one of the three fixtures with two body styles
(hatchback vs sedan, see parsers/mazda.py), hence the extra assertions
splitting its variants by `model`."""

from pathlib import Path

from scraper.parsers.mazda import MazdaParser

FIXTURES = Path(__file__).parent / "fixtures"
CX5 = FIXTURES / "mazda_cx-5_cenik.pdf"
MAZDA3 = FIXTURES / "mazda3_cenik.pdf"
CX30 = FIXTURES / "mazda_cx-30_cenik.pdf"


def _variant(variants, model: str, trim: str, engine_fragment: str):
    return next(v for v in variants if v.model == model and v.trim == trim and engine_fragment in v.variant_name)


def test_mazda_parser_extracts_cx5_variants() -> None:
    # 4 trims (2WD) + 3 trims (AWD, no Prime-Line) = 7 rows, all on the one price page
    variants = MazdaParser().parse(CX5)
    assert len(variants) == 7
    assert all(v.model == "CX-5" for v in variants)
    assert all(v.currency == "CZK" for v in variants)
    assert all(v.powertrain == "ICE" for v in variants)
    assert all(v.source_page == 8 for v in variants)

    prime_line = _variant(variants, "CX-5", "Prime-Line", "2WD")
    assert prime_line.price == 875_900.0  # list price (CENA) - not the 824 900 Kč promotional "akční cena"

    awd_centre = _variant(variants, "CX-5", "Centre-Line", "AWD")
    assert awd_centre.price == 1_021_900.0

    awd_homura = _variant(variants, "CX-5", "Homura", "AWD")
    assert awd_homura.price == 1_155_900.0


def test_mazda_parser_extracts_mazda3_variants_split_by_body_style() -> None:
    variants = MazdaParser().parse(MAZDA3)
    hatchback = [v for v in variants if v.model == "3"]
    sedan = [v for v in variants if v.model == "3 Sedan"]

    assert len(hatchback) == 30
    assert len(sedan) == 12
    assert len(variants) == len(hatchback) + len(sedan)  # no third/unexpected model slipped through
    assert all(v.source_page in (16, 17) for v in hatchback)
    assert all(v.source_page == 18 for v in sedan)

    assert _variant(hatchback, "3", "Prime-line", "6MT").price == 664_900.0
    assert _variant(sedan, "3 Sedan", "Prime-line", "6MT").price == 664_900.0  # same base trim/engine, same price

    homura_plus = _variant(hatchback, "3", "Homura Plus", "6AT")
    assert homura_plus.price == 881_400.0


def test_mazda_parser_extracts_cx30_variants() -> None:
    # 6 trims x 2 engine tiers x 2-3 model-year price waves = 32 rows across 2 pages
    variants = MazdaParser().parse(CX30)
    assert len(variants) == 32
    assert all(v.model == "CX-30" for v in variants)
    assert all(v.source_page in (11, 12) for v in variants)

    prime_line = next(v for v in variants if v.trim == "Prime-line")
    assert prime_line.price == 721_090.0

    takumi_prices = {v.price for v in variants if v.trim == "Takumi"}
    assert 897_490.0 in takumi_prices


def test_mazda_parser_skips_malformed_rows_rather_than_guessing() -> None:
    # Mazda3's sedan section has one row with no recoverable trim name and
    # one with an extra, un-attributable price column merged in (both
    # verified by hand against the source PDF) - both must be dropped, not
    # guessed at.
    variants = MazdaParser().parse(MAZDA3)
    sedan = [v for v in variants if v.model == "3 Sedan"]
    assert all(v.trim for v in sedan)
    assert all(v.price is not None and v.price > 0 for v in sedan)


def test_mazda_parser_raw_text_traceable_to_source() -> None:
    variants = MazdaParser().parse(CX5)
    variant = _variant(variants, "CX-5", "Prime-Line", "2WD")
    assert "875 900" in variant.raw_text
    assert variant.source_page == 8

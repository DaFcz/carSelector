"""Tests for CupraParser on all six real per-model price lists (downloaded
2026-09-12 from cupraofficial.cz's asset CDN, effective 26 May-17 August
2026 depending on model — see scraper/tests/fixtures/cupra_*.pdf). Prices
are transcribed by hand from the PDF text, so it can always be verified
that the extraction matches the source — same discipline as
test_kia_parser.py.

Row counts per fixture (17/16/20/10/4/5) were cross-checked by hand
against `page.extract_words()`/`group_into_lines` output for every
fixture, not just spot-checked - see parsers/cupra.py's module docstring
for the layout quirk (`extract_text()` visually scrambling some rows)
that makes trusting raw extracted text risky here, confirmed against a
rendered page image for Terramar."""

from pathlib import Path

from scraper.parsers.cupra import CupraParser

FIXTURES = Path(__file__).parent / "fixtures"
LEON = FIXTURES / "cupra_leon_cenik.pdf"
LEON_SPORTSTOURER = FIXTURES / "cupra_leon_sportstourer_cenik.pdf"
FORMENTOR = FIXTURES / "cupra_formentor_cenik.pdf"
TERRAMAR = FIXTURES / "cupra_terramar_cenik.pdf"
BORN = FIXTURES / "cupra_born_cenik.pdf"
RAVAL = FIXTURES / "cupra_raval_cenik.pdf"


def _variant(variants, trim: str, engine_fragment: str):
    return next(v for v in variants if v.trim == trim and engine_fragment in v.variant_name)


def test_cupra_parser_extracts_leon_variants_across_two_price_tables() -> None:
    # Main table (CUPRA/VZ/VZ Extreme, page 2) = 4+3+3 = 10 rows, plus a
    # second "Tribe" special-edition table further into the same document
    # (page 16, Tribe/Tribe VZ = 4+3 = 7 rows) -> 17 total.
    variants = CupraParser().parse(LEON)
    assert len(variants) == 17
    assert all(v.model == "Leon" for v in variants)
    assert all(v.currency == "CZK" for v in variants)

    base = _variant(variants, "CUPRA", "1.5 TSI 150k")
    assert base.price == 809_900.0
    assert base.powertrain == "ICE"
    assert base.source_page == 2

    mhev = _variant(variants, "CUPRA", "1.5 eTSI 150k DSG")
    assert mhev.powertrain == "MHEV"

    phev = _variant(variants, "VZ Extreme", "e-HYBRID 272k DSG")
    assert phev.powertrain == "PHEV"
    assert phev.price == 1_494_900.0

    tribe = _variant(variants, "Tribe", "1.5 TSI 150k")
    assert tribe.price == 889_900.0
    assert tribe.source_page == 16


def test_cupra_parser_ignores_promo_price_and_reads_list_price() -> None:
    # Leon Sportstourer's "2.0 TSI 204k DSG 4WD" CUPRA row carries both a
    # base price and a discounted one on the same line - price must be the
    # base (first) one, not the promotional one.
    variants = CupraParser().parse(LEON_SPORTSTOURER)
    row = _variant(variants, "CUPRA", "2.0 TSI 204k DSG 4WD")
    assert row.price == 1_009_900.0
    assert "1,009,900" in row.raw_text
    assert "954,900" in row.raw_text  # promo price still visible for verification, just not used as `price`


def test_cupra_parser_extracts_formentor_variants_including_vz5() -> None:
    # Main table (11) + Tribe table (8) + a single-row VZ5 table further
    # into the document (1) = 20.
    variants = CupraParser().parse(FORMENTOR)
    assert len(variants) == 20
    assert all(v.model == "Formentor" for v in variants)

    vz5 = _variant(variants, "VZ5", "2.5 TSI 390k DSG 4WD")
    assert vz5.price == 1_694_900.0
    assert vz5.powertrain == "ICE"

    # Formentor's own price formatting uses comma thousands separators
    # ("934,900"), unlike Leon's space-separated ones - both must parse
    # to the same kind of plain float.
    base = _variant(variants, "CUPRA", "1.5 TSI 150k")
    assert base.price == 934_900.0


def test_cupra_parser_extracts_terramar_variants_with_offset_consumption_row() -> None:
    # Terramar's own PDF renders the consumption figure at a slightly
    # different y-offset than the rest of its row (verified against a
    # rendered page image) - naive extract_text() scrambles the reading
    # order, but group_into_lines's tolerance still merges it correctly.
    # Main table (CUPRA/VZ = 3+2) + a second "Tribe Edition"/"Tribe VZ
    # Edition" table further into the document (3+2) = 10.
    variants = CupraParser().parse(TERRAMAR)
    assert len(variants) == 10
    assert all(v.model == "Terramar" for v in variants)

    row = _variant(variants, "CUPRA", "2.0 TSI 204k DSG 4WD")
    assert row.price == 1_179_900.0

    tribe = _variant(variants, "Tribe Edition", "2.0 TSI 204k DSG 4WD")
    assert tribe.price == 1_249_900.0


def test_cupra_parser_extracts_born_electric_variants_and_skips_incomplete_row() -> None:
    # Born's own price list lists a base "50 kWh" trim with only a price
    # and no power/transmission/consumption/CO2 (verified against the
    # rendered page - a real gap in CUPRA's own published price list) -
    # must be skipped, not guessed at. 58 kWh/79 kWh (BORN), 79 kWh (VZ),
    # and 58 kWh (Akční model REBORN) all have complete rows -> 4 total.
    variants = CupraParser().parse(BORN)
    assert len(variants) == 4
    assert all(v.model == "Born" for v in variants)
    assert all(v.powertrain == "EV" for v in variants)
    assert all("50 kWh" not in v.variant_name for v in variants)

    top = _variant(variants, "VZ", "79 kWh")
    assert top.price == 1_354_900.0


def test_cupra_parser_extracts_raval_electric_variants() -> None:
    variants = CupraParser().parse(RAVAL)
    assert len(variants) == 5
    assert all(v.model == "Raval" for v in variants)
    assert all(v.powertrain == "EV" for v in variants)
    assert {v.trim for v in variants} == {"Akční model ROOKIE", "RAVAL", "PLUS", "ENDURANCE", "VZ"}

    endurance = _variant(variants, "ENDURANCE", "55,2 kWh")
    assert endurance.price == 879_900.0


def test_cupra_parser_raw_text_traceable_to_source() -> None:
    variants = CupraParser().parse(LEON)
    variant = _variant(variants, "CUPRA", "1.5 TSI 150k")
    assert "809 900" in variant.raw_text
    assert variant.source_page == 2

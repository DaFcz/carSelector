"""Tests for DaciaParser on all six real per-model price lists (downloaded
2026-09-07 from dacia.cz's asset CDN, effective 1 July/1 August 2026 — see
scraper/tests/fixtures/dacia_*.pdf). Prices are transcribed by hand from
the PDF text, so it can always be verified that the extraction matches the
source — same discipline as test_kia_parser.py.

Row counts per fixture (19/9/10/22/17/3) were cross-checked by hand against
`page.extract_words()` output for every fixture, not just spot-checked —
see parsers/dacia.py's module docstring for the row/cluster shape this
relies on."""

from pathlib import Path

from scraper.parsers.dacia import DaciaParser

FIXTURES = Path(__file__).parent / "fixtures"
DUSTER = FIXTURES / "dacia_duster_cenik.pdf"
SANDERO = FIXTURES / "dacia_sandero_cenik.pdf"
STEPWAY = FIXTURES / "dacia_sandero_stepway_cenik.pdf"
JOGGER = FIXTURES / "dacia_jogger_cenik.pdf"
BIGSTER = FIXTURES / "dacia_bigster_cenik.pdf"
SPRING = FIXTURES / "dacia_spring_cenik.pdf"


def _variant(variants, trim: str, engine_fragment: str):
    return next(v for v in variants if v.trim == trim and engine_fragment in v.variant_name)


def test_dacia_parser_extracts_duster_variants() -> None:
    # Essential is LPG-only (1 row); Expression/Journey/Extreme each get
    # all 6 engines -> 1 + 6 + 6 + 6 = 19 rows, all on the one price page.
    variants = DaciaParser().parse(DUSTER)
    assert len(variants) == 19
    assert all(v.model == "Duster" for v in variants)
    assert all(v.currency == "CZK" for v in variants)
    assert all(v.source_page == 3 for v in variants)

    essential = _variant(variants, "Essential", "Eco-G 120")
    assert essential.price == 441_900.0
    assert essential.powertrain == "ICE"

    mild = _variant(variants, "Expression", "mild hybrid 140")
    assert mild.powertrain == "MHEV"
    assert mild.price == 527_900.0

    hev = _variant(variants, "Extreme", "hybrid 155")
    assert hev.powertrain == "HEV"
    assert hev.price == 629_900.0


def test_dacia_parser_strips_lpg_calculator_annotation() -> None:
    # "Dacia LPG Kalkulačka" is a link label, not part of the engine name -
    # must not leak into variant_name, but raw_text keeps it for
    # traceability against the source.
    variants = DaciaParser().parse(DUSTER)
    essential = _variant(variants, "Essential", "Eco-G 120")
    assert essential.variant_name == "Duster Essential Eco-G 120"
    assert "Kalkulačka" in essential.raw_text


def test_dacia_parser_extracts_sandero_and_stepway_variants() -> None:
    sandero = DaciaParser().parse(SANDERO)
    assert len(sandero) == 9
    assert all(v.model == "Sandero" for v in sandero)
    assert _variant(sandero, "Essential", "TCe 100").price == 339_900.0
    assert _variant(sandero, "Journey", "Hybrid 155").powertrain == "HEV"

    stepway = DaciaParser().parse(STEPWAY)
    assert len(stepway) == 10
    assert all(v.model == "Sandero Stepway" for v in stepway)
    assert _variant(stepway, "Extreme", "TCe 110").price == 443_900.0


def test_dacia_parser_extracts_bigster_variants() -> None:
    variants = DaciaParser().parse(BIGSTER)
    assert len(variants) == 17
    assert all(v.model == "Bigster" for v in variants)

    mild_g = _variant(variants, "Essential", "mild hybrid-G 140")
    assert mild_g.powertrain == "MHEV"
    assert mild_g.price == 556_900.0

    hev_4x4 = _variant(variants, "Journey", "hybrid 150 4×4")
    assert hev_4x4.powertrain == "HEV"
    assert hev_4x4.price == 750_900.0


def test_dacia_parser_extracts_spring_electric_variants() -> None:
    # Spring's cover/table font renders trim names in inconsistent case
    # ("EssEntial", "EXPREssiOn", "EXtREME") - must still normalize to the
    # same "Essential"/"Expression"/"Extreme" spelling as every other model.
    variants = DaciaParser().parse(SPRING)
    assert len(variants) == 3
    assert all(v.model == "Spring" for v in variants)
    assert all(v.powertrain == "EV" for v in variants)
    assert {v.trim for v in variants} == {"Essential", "Expression", "Extreme"}

    top = _variant(variants, "Extreme", "electric 100")
    assert top.price == 489_900.0


def test_dacia_parser_extracts_jogger_5_and_7_seat_tables_separately() -> None:
    # One page holds two full price tables (5 míst / 7 míst), not two
    # columns of one table - 11 rows each.
    variants = DaciaParser().parse(JOGGER)
    assert len(variants) == 22
    assert all(v.model == "Jogger" for v in variants)

    five_seat = [v for v in variants if "5 míst" in v.variant_name]
    seven_seat = [v for v in variants if "7 míst" in v.variant_name]
    assert len(five_seat) == 11
    assert len(seven_seat) == 11

    five = _variant(five_seat, "Essential", "Eco-G 120")
    seven = _variant(seven_seat, "Essential", "Eco-G 120")
    assert five.price == 425_500.0
    assert seven.price == 455_500.0
    assert five.price != seven.price
    assert five.variant_name != seven.variant_name  # dedup key for import_scraper_data.py


def test_dacia_parser_raw_text_traceable_to_source() -> None:
    variants = DaciaParser().parse(DUSTER)
    variant = _variant(variants, "Essential", "Eco-G 120")
    assert "441" in variant.raw_text
    assert "900" in variant.raw_text
    assert variant.source_page == 3

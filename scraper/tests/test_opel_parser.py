"""Tests for OpelParser on all eleven real per-model/powertrain price
lists (downloaded 2026-09-12/13 from opel.cz, effective 7-30 September
2026 — see scraper/tests/fixtures/opel_*.pdf). Prices and row counts are
transcribed by hand from `page.extract_text()`/`extract_words()` output
for every fixture, not just spot-checked — same discipline as
test_renault_parser.py."""

from pathlib import Path

from scraper.parsers.opel import OpelParser

FIXTURES = Path(__file__).parent / "fixtures"
CORSA = FIXTURES / "opel_corsa_cenik.pdf"
CORSA_ELECTRIC = FIXTURES / "opel_corsa_electric_cenik.pdf"
ASTRA_HB = FIXTURES / "opel_astra_hb_cenik.pdf"
ASTRA_ST = FIXTURES / "opel_astra_st_cenik.pdf"
ASTRA_ELECTRIC = FIXTURES / "opel_astra_electric_cenik.pdf"
MOKKA = FIXTURES / "opel_mokka_cenik.pdf"
MOKKA_ELECTRIC = FIXTURES / "opel_mokka_electric_cenik.pdf"
FRONTERA = FIXTURES / "opel_frontera_cenik.pdf"
FRONTERA_ELECTRIC = FIXTURES / "opel_frontera_electric_cenik.pdf"
GRANDLAND = FIXTURES / "opel_grandland_cenik.pdf"
GRANDLAND_ELECTRIC = FIXTURES / "opel_grandland_electric_cenik.pdf"


def _variant(variants, trim: str, engine_fragment: str):
    return next(v for v in variants if v.trim == trim and engine_fragment in v.variant_name)


def test_opel_parser_extracts_corsa_variants_with_two_distinct_hybrid_powers() -> None:
    # Edition(ICE+MHEV) + YES(ICE+MHEV) + GS(ICE + two distinct MHEV
    # power outputs) = 7. The two GS hybrid rows share the same trim and
    # both say plain "Hybrid 1.2 TURBO ... Start/Stop eDCT6" apart from
    # their own power figure ("(81kW/110k)" vs "(107kW/145k)") - a
    # regression test for a bug where a wide MOTOR sub-line like the power
    # figure was misclassified into the next column and silently dropped,
    # making both rows produce an identical variant_name/price collision.
    variants = OpelParser().parse(CORSA)
    assert len(variants) == 7
    assert all(v.model == "Corsa" for v in variants)
    assert all(v.currency == "CZK" for v in variants)

    gs_low = _variant(variants, "GS", "(81kW/110k)")
    gs_high = _variant(variants, "GS", "(107kW/145k)")
    assert gs_low.price == 589_990.0
    assert gs_high.price == 629_990.0
    assert gs_low.powertrain == gs_high.powertrain == "MHEV"

    base = _variant(variants, "Edition", "1.2 TURBO (74kW/100k)")
    assert base.price == 459_990.0
    assert base.powertrain == "ICE"


def test_opel_parser_extracts_corsa_electric_variants() -> None:
    variants = OpelParser().parse(CORSA_ELECTRIC)
    assert len(variants) == 2
    assert all(v.model == "Corsa" for v in variants)
    assert all(v.powertrain == "EV" for v in variants)
    assert {v.trim for v in variants} == {"Edition", "GS"}

    edition = _variant(variants, "Edition", "Elektromotor")
    assert edition.price == 809_990.0


def test_opel_parser_extracts_astra_hb_variants_with_diesel_and_phev() -> None:
    # Edition/GS(ICE+MHEV+PHEV) + Ultimate(MHEV+PHEV, no diesel trim) = 8.
    variants = OpelParser().parse(ASTRA_HB)
    assert len(variants) == 8
    assert all(v.model == "Astra" for v in variants)

    diesel = _variant(variants, "Edition", "1.5 CDTI")
    assert diesel.powertrain == "ICE"
    assert diesel.price == 639_990.0

    phev = _variant(variants, "Ultimate", "1.6 TURBO (143 kW/195k) PHEV")
    assert phev.powertrain == "PHEV"
    assert phev.price == 1_039_990.0


def test_opel_parser_extracts_astra_st_variants() -> None:
    # Edition/GS/Ultimate, each ICE+MHEV+PHEV = 9.
    variants = OpelParser().parse(ASTRA_ST)
    assert len(variants) == 9
    assert all(v.model == "Astra" for v in variants)
    assert {v.trim for v in variants} == {"Edition", "GS", "Ultimate"}


def test_opel_parser_extracts_astra_electric_variants_with_body_style_in_trim() -> None:
    # Astra Electric covers both body styles in one document - each of the
    # 3 trims appears twice (Hatchback + Sports Tourer) = 6.
    variants = OpelParser().parse(ASTRA_ELECTRIC)
    assert len(variants) == 6
    assert all(v.model == "Astra" for v in variants)
    assert all(v.powertrain == "EV" for v in variants)
    assert {v.trim for v in variants} == {
        "Edition Hatchback",
        "Edition Sports Tourer",
        "GS Hatchback",
        "GS Sports Tourer",
        "Ultimate Hatchback",
        "Ultimate Sports Tourer",
    }

    hatchback = _variant(variants, "Edition Hatchback", "Elektromotor")
    sports_tourer = _variant(variants, "Edition Sports Tourer", "Elektromotor")
    assert hatchback.price == 979_990.0
    assert sports_tourer.price == 999_990.0


def test_opel_parser_extracts_mokka_variants() -> None:
    variants = OpelParser().parse(MOKKA)
    assert len(variants) == 4
    assert all(v.model == "Mokka" for v in variants)
    assert {v.trim for v in variants} == {"Edition", "GS"}


def test_opel_parser_extracts_mokka_electric_variants_despite_mislabeled_header() -> None:
    # Mokka Electric's own header prints "MOTOR MOTOR" instead of
    # "LCDV KÓD MOTOR" - a regression test for _column_anchors's handling
    # of that document-specific quirk (see its own docstring).
    variants = OpelParser().parse(MOKKA_ELECTRIC)
    assert len(variants) == 3
    assert all(v.model == "Mokka" for v in variants)
    assert all(v.powertrain == "EV" for v in variants)
    assert {v.trim for v in variants} == {"Edition", "GS", "GSE"}

    gse = _variant(variants, "GSE", "Elektromotor")
    assert gse.price == 1_209_990.0


def test_opel_parser_extracts_frontera_variants() -> None:
    variants = OpelParser().parse(FRONTERA)
    assert len(variants) == 4
    assert all(v.model == "Frontera" for v in variants)
    assert all(v.powertrain == "MHEV" for v in variants)


def test_opel_parser_extracts_frontera_electric_variants_with_xl_trim() -> None:
    variants = OpelParser().parse(FRONTERA_ELECTRIC)
    assert len(variants) == 4
    assert all(v.model == "Frontera" for v in variants)
    assert {v.trim for v in variants} == {"Edition", "Edition XL", "GS", "GS XL"}


def test_opel_parser_extracts_grandland_variants() -> None:
    # Edition/GS/Ultimate, each MHEV+PHEV = 6.
    variants = OpelParser().parse(GRANDLAND)
    assert len(variants) == 6
    assert all(v.model == "Grandland" for v in variants)

    phev = _variant(variants, "Ultimate", "PHEV")
    assert phev.powertrain == "PHEV"
    assert phev.price == 1_119_990.0


def test_opel_parser_extracts_grandland_electric_variants_with_awd_trim() -> None:
    # A regression test for a bug where the DOJEZD column's own "km" unit
    # bled into the CENÍKOVÁ bucket for the widest row (Ultimate 4x4's
    # dual-motor description), corrupting the price string.
    variants = OpelParser().parse(GRANDLAND_ELECTRIC)
    assert len(variants) == 3
    assert all(v.model == "Grandland" for v in variants)
    assert all(v.powertrain == "EV" for v in variants)

    awd = _variant(variants, "Ultimate 4x4", "elektromotor")
    assert awd.price == 1_349_990.0
    assert "4x4" in awd.trim


def test_opel_parser_raw_text_traceable_to_source() -> None:
    variants = OpelParser().parse(CORSA)
    variant = _variant(variants, "Edition", "1.2 TURBO (74kW/100k)")
    assert "459" in variant.raw_text
    assert "990" in variant.raw_text
    assert variant.source_page == 1

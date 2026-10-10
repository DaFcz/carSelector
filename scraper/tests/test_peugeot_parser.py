"""Tests for PeugeotParser on all seven real per-model price lists
(downloaded 2026-09-13 from peugeot.ecpaper.cz, effective September 2026 -
see scraper/tests/fixtures/peugeot_*.pdf). Prices and row counts are
transcribed by hand from `page.extract_text()` output for every fixture,
not just spot-checked - same discipline as test_opel_parser.py."""

from pathlib import Path

from scraper.parsers.peugeot import PeugeotParser

FIXTURES = Path(__file__).parent / "fixtures"
P208 = FIXTURES / "peugeot_208_cenik.pdf"
P2008 = FIXTURES / "peugeot_2008_cenik.pdf"
P308SW = FIXTURES / "peugeot_308sw_cenik.pdf"
P3008 = FIXTURES / "peugeot_3008_cenik.pdf"
P408 = FIXTURES / "peugeot_408_cenik.pdf"
P5008 = FIXTURES / "peugeot_5008_cenik.pdf"
RIFTER = FIXTURES / "peugeot_rifter_cenik.pdf"


def _variant(variants, trim: str, engine_fragment: str):
    return next(v for v in variants if v.trim == trim and engine_fragment in v.variant_name)


def test_peugeot_parser_extracts_208_variants() -> None:
    # STYLE(ICE+MHEV+EV+EV) + EDITION(ICE+MHEV) + BUSINESS(ICE+MHEV+EV+EV)
    # + ALLURE(ICE+MHEV+MHEV+EV+EV) + GT(MHEV+EV) = 17.
    variants = PeugeotParser().parse(P208)
    assert len(variants) == 17
    assert all(v.model == "208" for v in variants)
    assert all(v.currency == "CZK" for v in variants)

    base = _variant(variants, "STYLE", "Turbo 100 MAN6")
    assert base.price == 470_000.0
    assert base.powertrain == "ICE"

    ev = _variant(variants, "STYLE", "Elektromotor 100 kW")
    assert ev.price == 725_000.0
    assert ev.powertrain == "EV"
    assert "Dojezd: 362 km" in ev.variant_name


def test_peugeot_parser_extracts_2008_variants() -> None:
    variants = PeugeotParser().parse(P2008)
    assert len(variants) == 14
    assert all(v.model == "2008" for v in variants)

    mhev = _variant(variants, "GT", "Hybrid 145 e-DCS6")
    assert mhev.powertrain == "MHEV"
    assert mhev.price == 750_000.0


def test_peugeot_parser_extracts_308sw_variants_with_diesel_and_phev() -> None:
    # STYLE(MHEV+ICE) + ALLURE(MHEV+ICE+PHEV+EV) + GT(MHEV+ICE+PHEV+EV) = 10.
    variants = PeugeotParser().parse(P308SW)
    assert len(variants) == 10
    assert all(v.model == "308 SW" for v in variants)

    diesel = _variant(variants, "STYLE", "BlueHDi 130 EAT8")
    assert diesel.powertrain == "ICE"
    assert diesel.price == 710_000.0

    phev = _variant(variants, "GT", "Plug-in HYBRID 195 e-DCS7")
    assert phev.powertrain == "PHEV"
    assert phev.price == 1_135_000.0


def test_peugeot_parser_extracts_3008_variants_with_dual_motor_awd() -> None:
    # A regression test: BUSINESS's own HYBRID row packs trim + engine +
    # price onto ONE physical line (no discount/promo columns) and pushes
    # the CO2 figure onto a separate line by itself, reversing the usual
    # "engine line(s) then price line" order - the price must still come
    # out clean, without the CO2/price text bleeding into variant_name.
    variants = PeugeotParser().parse(P3008)
    assert len(variants) == 12
    assert all(v.model == "3008" for v in variants)

    business_mhev = _variant(variants, "BUSINESS", "HYBRID 145 AUT")
    assert business_mhev.price == 759_000.0
    assert "000" not in business_mhev.variant_name

    awd = _variant(variants, "ALLURE", "Dual Motor AWD")
    assert awd.powertrain == "EV"
    assert awd.price == 1_280_000.0


def test_peugeot_parser_extracts_408_variants() -> None:
    variants = PeugeotParser().parse(P408)
    assert len(variants) == 4
    assert all(v.model == "408" for v in variants)
    assert {v.trim for v in variants} == {"ALLURE", "GT"}


def test_peugeot_parser_extracts_5008_variants() -> None:
    variants = PeugeotParser().parse(P5008)
    assert len(variants) == 12
    assert all(v.model == "5008" for v in variants)
    assert {v.trim for v in variants} == {"ALLURE", "BUSINESS", "GT"}


def test_peugeot_parser_extracts_rifter_variants_with_two_body_lengths() -> None:
    # RIFTER: ALLURE(ICE+ICE+EV) + GT(ICE+EV) = 5.
    # RIFTER LONG: ALLURE(ICE+ICE+EV) + GT(ICE+EV) = 5. Total 10.
    # The document's own "S HOMOLOGACÍ N1" (light-commercial type-approval)
    # sections are out of scope, same convention as every other brand's
    # own commercial-vehicle exclusions - must not appear at all.
    variants = PeugeotParser().parse(RIFTER)
    assert len(variants) == 10
    assert {v.model for v in variants} == {"Rifter", "Rifter LONG"}
    assert all("HOMOLOGAC" not in v.model.upper() for v in variants)

    plain = _variant(variants, "ALLURE", "ELECTRIC 135")
    long = next(v for v in variants if v.model == "Rifter LONG" and v.trim == "ALLURE" and "ELECTRIC" in v.variant_name)
    assert plain.model == "Rifter"
    assert plain.price == 960_000.0
    assert long.price == 995_000.0


def test_peugeot_parser_raw_text_traceable_to_source() -> None:
    variants = PeugeotParser().parse(P208)
    variant = _variant(variants, "STYLE", "Turbo 100 MAN6")
    assert "470" in variant.raw_text
    assert "000" in variant.raw_text
    assert variant.source_page == 2

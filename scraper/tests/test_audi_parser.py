"""Tests for AudiParser on a real response from Audi's own web-
configurator JSON API (downloaded 2026-09-14 from konfigurator.audi.cz -
see scraper/tests/fixtures/audi_modelgroup.json). Row counts and prices
are cross-checked by hand against the raw JSON, not just spot-checked -
same discipline as every other brand's own parser tests here."""
from pathlib import Path

from scraper.parsers.audi import AudiParser

FIXTURE = Path(__file__).parent / "fixtures" / "audi_modelgroup.json"


def _variant(variants, model: str, trim: str, engine_fragment: str):
    return next(v for v in variants if v.model == model and v.trim == trim and engine_fragment in v.variant_name)


def test_audi_parser_extracts_every_model_and_engine_row() -> None:
    # 22 model groups, 1-5 variants each, 1-5 engines per variant - hand-
    # summed from the fixture's own modelgroups/variants/models nesting.
    variants = AudiParser().parse(FIXTURE)
    assert len(variants) == 110
    assert all(v.currency == "CZK" for v in variants)
    assert all(v.price is not None and v.price > 0 for v in variants)


def test_audi_parser_extracts_s_line_as_a_real_trim() -> None:
    # "S line" is the same car, same engine, at a fixed markup over the
    # base ("A3") variant - a genuine trim, not a separate model.
    variants = AudiParser().parse(FIXTURE)
    base = _variant(variants, "A3 Limuzína", "Standard", "Diesel")
    sline = _variant(variants, "A3 Limuzína", "S line", "Diesel")
    assert base.price == 975_900.0
    assert sline.price == 1_037_900.0
    assert base.powertrain == sline.powertrain == "ICE"


def test_audi_parser_promotes_performance_variants_to_their_own_model() -> None:
    # S3/RS3 are Audi's own separate performance models (same convention
    # as BMW's M2/M4 in this scraper), not oddly-priced trims of A3.
    variants = AudiParser().parse(FIXTURE)
    s3 = _variant(variants, "S3 Limuzína", "Standard", "quattro")
    rs3 = _variant(variants, "RS3 Limuzína", "Standard", "quattro")
    assert s3.price == 1_418_900.0
    assert rs3.price == 1_775_900.0
    assert not any(v.model == "A3 Limuzína" and "S3" in v.variant_name for v in variants)


def test_audi_parser_handles_group_specific_naming_quirks() -> None:
    # Regression tests for two observed inconsistencies in the API's own
    # data: "Q4 e-tron PI"/"Q4 Sportback e-tron PI" carry a trailing
    # internal-code artifact their own variants don't have (stripped);
    # "SQ5"/"S6 Sportback"-style promoted names sometimes already include
    # the modelgroup's own body-style word and sometimes don't, so it
    # must be appended only when genuinely missing (not duplicated).
    variants = AudiParser().parse(FIXTURE)
    models = {v.model for v in variants}
    assert "Q4 e-tron" in models
    assert "Q4 Sportback e-tron" in models
    assert not any("PI" in m for m in models)

    assert "SQ5 Sportback" in models  # body style appended (bare "SQ5" badge otherwise)
    assert "S6 Sportback" in models  # NOT "S6 Sportback Sportback e-tron" (already complete)
    assert "S6 Sportback Sportback e-tron" not in models


def test_audi_parser_strips_redundant_audi_prefix() -> None:
    # Q3/Q5/Q6/Q8's own variant names are prefixed "Audi " (unlike A3/A5/
    # A6/e-tron GT's) - left in place, `f"{brand} {model}"` would read
    # "Audi Audi Q5".
    variants = AudiParser().parse(FIXTURE)
    assert any(v.model == "Q5" for v in variants)
    assert not any(v.model.startswith("Audi ") for v in variants)


def test_audi_parser_classifies_powertrains() -> None:
    variants = AudiParser().parse(FIXTURE)

    mhev = _variant(variants, "A3 Limuzína", "Standard", "mild) Hybrid")
    assert mhev.powertrain == "MHEV"

    phev = _variant(variants, "A5 Limuzína", "Standard", "Plug-in hybrid")
    assert phev.powertrain == "PHEV"

    ev = _variant(variants, "Q4 e-tron", "Standard", "Elektro")
    assert ev.powertrain == "EV"
    assert "dojezd" in ev.variant_name


def test_audi_parser_keeps_drivetrain_text_for_downstream_classification() -> None:
    # AudiParser doesn't classify drivetrain itself - it just has to keep
    # wheelDrive's own text ("Přední"/"Zadní"/"quattro®") in variant_name
    # so scripts/import_scraper_data.py's infer_drivetrain (which already
    # matches "quattro", and gained a "zadní" check for MG) reads it
    # correctly with no Audi-specific fix needed.
    variants = AudiParser().parse(FIXTURE)
    fwd = _variant(variants, "A3 Limuzína", "Standard", "mild) Hybrid")
    awd = _variant(variants, "S3 Limuzína", "Standard", "quattro")
    rwd = _variant(variants, "Q4 e-tron", "Standard", "Zadní")
    assert "Přední" in fwd.variant_name
    assert "quattro" in awd.variant_name
    assert "Zadní" in rwd.variant_name


def test_audi_parser_raw_text_traceable_to_source() -> None:
    variants = AudiParser().parse(FIXTURE)
    variant = _variant(variants, "A3 Limuzína", "Standard", "Diesel")
    assert "975900" in variant.raw_text
    assert variant.source_page == 1

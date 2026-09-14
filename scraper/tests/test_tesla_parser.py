"""Tests for TeslaParser on real Design Studio pages for both models
currently sold in the Czech Republic (downloaded 2026-09-14 from
https://www.tesla.com/cs_cz/modely/design and .../model3/design via an
interactive browser session - see parsers/tesla.py's own module docstring
for why a plain `requests`/Playwright fetch couldn't be used instead, and
scraper/tests/fixtures/tesla_modely_design.html/tesla_model3_design.html's
own `Lexicon.my`/`Lexicon.m3` payloads, which are the real, unmodified
API response - only the surrounding page markup around them is a minimal
reconstruction of the real `<script>const dataJson = {...}</script>`
embedding, not the full downloaded page). Prices are cross-checked by hand
against what actually rendered on the live page for each trim, not just
spot-checked - same discipline as every other brand's own parser tests
here."""
from pathlib import Path

from scraper.parsers.tesla import TeslaParser

FIXTURES = Path(__file__).parent / "fixtures"
MODEL_Y_FIXTURE = FIXTURES / "tesla_modely_design.html"
MODEL_3_FIXTURE = FIXTURES / "tesla_model3_design.html"


def _variant(variants, trim: str):
    return next(v for v in variants if v.trim == trim)


def test_tesla_parser_extracts_every_trim_for_model_y() -> None:
    # 4 TRIM-group options in the real response: base RWD, Premium Long
    # Range RWD, Premium Long Range AWD ("Dual Motor"), Performance AWD.
    variants = TeslaParser().parse(MODEL_Y_FIXTURE)
    assert len(variants) == 4
    assert all(v.model == "Model Y" for v in variants)
    assert all(v.powertrain == "EV" for v in variants)
    assert all(v.currency == "CZK" for v in variants)


def test_tesla_parser_reads_the_full_vat_included_price_not_the_addon() -> None:
    # Each TRIM option's own `pricing` list also carries a "base" entry
    # (the trim's own price ADD-ON, e.g. 105000 for the base RWD trim) -
    # not a usable standalone price. The parser must read "base_plus_trim"
    # instead, which matches what actually renders on the live page.
    variants = TeslaParser().parse(MODEL_Y_FIXTURE)
    base = _variant(variants, "Standard")
    performance = _variant(variants, "Performance")
    assert base.price == 1_004_990.0
    assert performance.price == 1_549_900.0


def test_tesla_parser_uses_standard_for_the_base_trim_with_no_category() -> None:
    # Tesla's own API omits `extra_copy_formatted.category` entirely for
    # the cheapest trim of each model (unlike "Premium"/"Performance",
    # which do carry one) - read as "Standard" here, same convention as
    # other brands' own base trims elsewhere in this scraper.
    variants = TeslaParser().parse(MODEL_Y_FIXTURE)
    assert _variant(variants, "Standard").price == 1_004_990.0


def test_tesla_parser_model_3_prices() -> None:
    variants = TeslaParser().parse(MODEL_3_FIXTURE)
    assert len(variants) == 4
    assert all(v.model == "Model 3" for v in variants)
    assert _variant(variants, "Standard").price == 899_990.0
    assert _variant(variants, "Performance").price == 1_405_990.0


def test_tesla_parser_keeps_drivetrain_wording_for_downstream_classification() -> None:
    # TeslaParser doesn't classify drivetrain itself - it keeps Tesla's own
    # long_name wording ("pohonem zadních kol"/"pohonem všech kol") in
    # variant_name so scripts/import_scraper_data.py's infer_drivetrain
    # (which gained a broader zadní* match and a "všech kol" AWD
    # alternative for this brand) reads it correctly.
    variants = TeslaParser().parse(MODEL_Y_FIXTURE)
    rwd = _variant(variants, "Standard")
    awd = _variant(variants, "Performance")
    assert "pohonem zadních kol" in rwd.variant_name
    assert "pohonem všech kol" in awd.variant_name


def test_tesla_parser_raw_text_traceable_to_source() -> None:
    variants = TeslaParser().parse(MODEL_Y_FIXTURE)
    variant = _variant(variants, "Standard")
    assert "1004990" in variant.raw_text
    assert variant.source_page == 1

"""Tests for MercedesBenzParser on the real combined price list (downloaded
2026-08-29 from mercedes-benz.cz, effective 27 May 2026 — see
scraper/tests/fixtures/mercedes_benz_cenik_souhrnny.pdf). Prices are
transcribed by hand from the PDF text, so it can always be verified that
the extraction matches the source — same discipline as test_kia_parser.py.

The fixture is the ENTIRE 74-page combined price list (see parsers/
mercedes_benz.py's module docstring for why one document covers every
Mercedes-Benz model) - these tests only check the four chapters this
scraper tracks (C-Class/C-Class Estate/E-Class/E-Class Estate), the same
document also contains ~65 other pages (A-Class, GLC, S-Class, EQS, AMG
GT, ...) that MercedesBenzParser is expected to skip."""

from pathlib import Path

from scraper.parsers.mercedes_benz import MercedesBenzParser

FIXTURE = Path(__file__).parent / "fixtures" / "mercedes_benz_cenik_souhrnny.pdf"


def _variant(variants, model: str, price_fragment: str):
    return next(v for v in variants if v.model == model and price_fragment in v.raw_text)


def test_mercedes_benz_parser_only_extracts_tracked_models() -> None:
    variants = MercedesBenzParser().parse(FIXTURE)
    assert len(variants) == 59
    assert {v.model for v in variants} == {"C-Class", "C-Class Estate", "E-Class", "E-Class Estate"}
    assert all(v.currency == "CZK" for v in variants)
    assert all(v.powertrain in ("MHEV", "PHEV") for v in variants)  # no plain-ICE trim in this lineup


def test_mercedes_benz_parser_extracts_c_class_sedan_variants() -> None:
    # Vznětové motory (diesel, 7 rows) + Zážehové motory (petrol, incl. 2 AMG, 10 rows)
    variants = [v for v in MercedesBenzParser().parse(FIXTURE) if v.model == "C-Class"]
    assert len(variants) == 17
    assert all(v.source_page in (21, 22) for v in variants)

    diesel = _variant(variants, "C-Class", "C 200 d 206.003")
    assert diesel.trim == "Vznětové motory"
    assert diesel.powertrain == "MHEV"
    assert diesel.price == 1_264_450.0  # VAT-inclusive price (row 2), not the 1 045 000 ex-VAT figure on row 1
    assert diesel.source_page == 21

    phev = _variant(variants, "C-Class", "C 300 de 4MATIC")
    assert phev.trim == "Vznětové motory"
    assert phev.powertrain == "PHEV"
    assert phev.price == 1_730_300.0

    # price above 999,999 Kč, split across multiple words in the PDF ("2" "885" "850")
    amg = _variant(variants, "C-Class", "Mercedes-AMG C 63 S E PERFORMANCE")
    assert amg.trim == "Zážehové motory"
    assert amg.powertrain == "PHEV"
    assert amg.price == 2_885_850.0
    assert amg.source_page == 22


def test_mercedes_benz_parser_extracts_c_class_estate_variants() -> None:
    # Vznětové motory (6 rows) + Zážehové motory (incl. 1 AMG, 8 rows)
    variants = [v for v in MercedesBenzParser().parse(FIXTURE) if v.model == "C-Class Estate"]
    assert len(variants) == 14
    assert all(v.source_page in (24, 25) for v in variants)

    diesel = _variant(variants, "C-Class Estate", "C 200 d kombi 206.203")
    assert diesel.trim == "Vznětové motory"
    assert diesel.price == 1_300_750.0


def test_mercedes_benz_parser_extracts_e_class_sedan_variants() -> None:
    # Vznětové motory (6 rows) + Zážehové motory (7 rows)
    variants = [v for v in MercedesBenzParser().parse(FIXTURE) if v.model == "E-Class"]
    assert len(variants) == 13
    assert all(v.source_page == 35 for v in variants)

    diesel = _variant(variants, "E-Class", "E 200 d 214.003")
    assert diesel.price == 1_583_890.0


def test_mercedes_benz_parser_extracts_e_class_estate_variants() -> None:
    # Vznětové motory (10 rows) + Zážehové motory (incl. 1 AMG, 5 rows)
    variants = [v for v in MercedesBenzParser().parse(FIXTURE) if v.model == "E-Class Estate"]
    assert len(variants) == 15
    assert all(v.source_page == 37 for v in variants)

    diesel = _variant(variants, "E-Class Estate", "E 200 d kombi 214.203")
    assert diesel.trim == "Vznětové motory"
    assert diesel.price == 1_645_600.0

    amg = _variant(variants, "E-Class Estate", "Mercedes-AMG E 53 HYBRID 4MATIC+ kombi")
    assert amg.trim == "Zážehové motory"
    assert amg.powertrain == "PHEV"
    assert amg.price == 2_873_750.0


def test_mercedes_benz_parser_raw_text_traceable_to_source() -> None:
    variants = MercedesBenzParser().parse(FIXTURE)
    variant = _variant(variants, "C-Class", "C 200 d 206.003")
    assert (
        "1 045 000" in variant.raw_text
    )  # ex-VAT price (row 1), kept for verification even though not stored as `price`
    assert "1 264 450" in variant.raw_text  # VAT-inclusive price (row 2) == variant.price
    assert variant.source_page == 21

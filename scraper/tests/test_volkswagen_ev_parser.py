"""Test for VolkswagenEvParser on real ID.4 and ID.3 Neo price lists
(downloaded 2026-07-19). Prices transcribed by hand from `extract_text()`
output, not derived from the parser — same discipline as the other tests.

ID.4 and ID.3 Neo deliberately have OPPOSITE power/battery order in the
description ("140 kW, 58 kWh" vs "50 kWh 125 kW") — that's why it's not
just tested on one of them, see the `volkswagen_ev.py` module docstring."""

from pathlib import Path

from scraper.parsers.volkswagen_ev import VolkswagenEvParser

ID4_FIXTURE = Path(__file__).parent / "fixtures" / "vw_id4_cenik.pdf"
ID3NEO_FIXTURE = Path(__file__).parent / "fixtures" / "vw_id3neo_cenik.pdf"


def _variant(variants, trim: str, fragment: str):
    return next(v for v in variants if v.trim == trim and fragment in v.variant_name)


def test_id4_prices_match_source_pdf() -> None:
    variants = VolkswagenEvParser().parse(ID4_FIXTURE)
    assert all(v.powertrain == "EV" for v in variants)
    assert all(v.model == "ID.4" for v in variants)

    # "ID.4 Pure 140 kW, 58 kWh E212JMA2 Automatická Zadní 792 562 Kč 959 000 Kč"
    assert _variant(variants, "Pure", "140 kW, 58 kWh").price == 959_000.0
    # "ID.4 Pro 4Motion" trim header, row abbreviated as "ID.4 Pro 4M 220 kW, 77 kWh ... 1 069 000 Kč"
    assert _variant(variants, "Pro 4Motion", "220 kW, 77 kWh").price == 1_069_000.0
    # "ID.4 GTX 250 kW 4M, 77 kWh E219VNA2 Automatická Všech kol 1 004 959 Kč 1 216 000 Kč"
    assert _variant(variants, "GTX", "250 kW").price == 1_216_000.0


def test_id3_neo_handles_reversed_battery_power_order() -> None:
    # Order is "50 kWh 125 kW" (battery first), not "125 kW, 50 kWh" like ID.4
    variants = VolkswagenEvParser().parse(ID3NEO_FIXTURE)
    assert all(v.model == "ID.3 Neo" for v in variants)

    # "ID.3 Neo Trend 50 kWh 125 kW E132HBA2 Automatická Zadní ... 749 000 Kč"
    assert _variant(variants, "Trend", "50 kWh 125 kW").price == 749_000.0
    # "ID.3 Neo Style 79 kWh 170 kW E134PPA2 Automatická Zadní ... 1 179 000 Kč"
    assert _variant(variants, "Style", "79 kWh 170 kW").price == 1_179_000.0


def test_no_suspiciously_low_prices() -> None:
    for fixture in (ID4_FIXTURE, ID3NEO_FIXTURE):
        variants = VolkswagenEvParser().parse(fixture)
        assert all(v.price >= 100_000 for v in variants)

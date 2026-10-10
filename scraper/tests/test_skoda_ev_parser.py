"""Test for SkodaEvParser on real Enyaq and Elroq price lists (downloaded
2026-07-19). Prices transcribed by hand from `extract_text()` output
(see the conversation history), not derived from the parser — same
discipline as the other tests.

Enyaq has two tables on ONE page (SUV and Coupé body styles) — unlike
ICE (where a second table is always on a different page), this required
the header to be looked up on every line as we go, not just once at the
start of the page (see `SkodaEvParser.parse`).

"Laurin & Klement" is assembled in two different ways in the PDF: for
Enyaq, "Laurin" is on the same line as "&"/"Klement" (like Superb in the
ICE price list); for Elroq, "Laurin" is on the line ABOVE the header (a
two-line split like "Exclusive Selection" for the Kodiaq) — both tested separately."""

from pathlib import Path

from scraper.parsers.skoda_ev import SkodaEvParser

ENYAQ_FIXTURE = Path(__file__).parent / "fixtures" / "skoda_enyaq_cenik.pdf"
ELROQ_FIXTURE = Path(__file__).parent / "fixtures" / "skoda_elroq_cenik.pdf"


def _variant(variants, trim: str, spec_fragment: str, body_style: str | None = None):
    return next(
        v
        for v in variants
        if v.trim == trim and spec_fragment in v.variant_name and (body_style is None or body_style in v.variant_name)
    )


def test_enyaq_finds_both_suv_and_coupe_tables_on_same_page() -> None:
    variants = SkodaEvParser().parse(ENYAQ_FIXTURE)
    assert len(variants) == 18
    assert all(v.powertrain == "EV" for v in variants)

    suv = [v for v in variants if "SUV" in v.variant_name]
    coupe = [v for v in variants if "Coupé" in v.variant_name]
    assert len(suv) == 9
    assert len(coupe) == 9
    assert {v.source_page for v in variants} == {3}


def test_enyaq_merges_laurin_a_klement_same_line() -> None:
    variants = SkodaEvParser().parse(ENYAQ_FIXTURE)
    assert not any(v.trim in ("Laurin", "&", "Klement") for v in variants)

    # SUV, "85 210 kW 82 kWh": "1 130 000 1 230 000 1 429 000 –"
    assert _variant(variants, "Selection", "85 210 kW 82 kWh", "SUV").price == 1_130_000.0
    assert _variant(variants, "Sportline", "85 210 kW 82 kWh", "SUV").price == 1_230_000.0
    assert _variant(variants, "Laurin & Klement", "85 210 kW 82 kWh", "SUV").price == 1_429_000.0

    # Coupé, "85x 220 kW 82 kWh": "1 250 000 1 350 000 1 549 000 –"
    assert _variant(variants, "Selection", "85x 220 kW 82 kWh", "Coupé").price == 1_250_000.0
    assert _variant(variants, "Laurin & Klement", "85x 220 kW 82 kWh", "Coupé").price == 1_549_000.0


def test_enyaq_rs_only_offered_for_rs_trim() -> None:
    # "RS 250 kW 82 kWh | 4×4 538-559 km – – – 1 350 000" (SUV)
    variants = SkodaEvParser().parse(ENYAQ_FIXTURE)
    rs_suv = _variant(variants, "RS", "RS 250 kW 82 kWh", "SUV")
    assert rs_suv.price == 1_350_000.0
    assert not any(v.trim != "RS" and "RS 250 kW" in v.variant_name for v in variants)


def test_elroq_merges_laurin_a_klement_from_continuation_line() -> None:
    # Elroq doesn't have "Laurin" on the main header line (just "&"/"Klement"),
    # but on the line above it — a different merge path than Enyaq/Superb.
    variants = SkodaEvParser().parse(ELROQ_FIXTURE)
    assert not any(v.trim in ("Laurin", "&", "Klement") for v in variants)
    assert any(v.trim == "Laurin & Klement" for v in variants)

    # "60 140 kW 61 kWh | zadní 408-453 km 882 000 948 000 1 012 000 – –"
    assert _variant(variants, "Essence", "60 140 kW 61 kWh").price == 882_000.0
    assert _variant(variants, "Selection", "60 140 kW 61 kWh").price == 948_000.0
    assert _variant(variants, "Sportline", "60 140 kW 61 kWh").price == 1_012_000.0


def test_no_suspiciously_low_prices() -> None:
    for fixture in (ENYAQ_FIXTURE, ELROQ_FIXTURE):
        variants = SkodaEvParser().parse(fixture)
        assert all(v.price >= 100_000 for v in variants)

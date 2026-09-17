"""Tests for opel_equipment.parse_equipment against the real fixtures
test_opel_parser.py uses, plus OpelParser's own wiring of the result onto
ExtractedVariant.equipment.

Item counts/names were cross-checked by hand against the fixtures' own
"STANDARDNÍ VÝBAVA" page - see opel_equipment.py's module docstring for
the two-column-per-line bullet layout this reads, and why the separate
"VÝBAVA NA PŘÁNÍ" (priced options) pages are a documented out-of-scope
gap rather than a parser bug."""
from pathlib import Path

from scraper.parsers.opel import OpelParser

FIXTURES = Path(__file__).parent / "fixtures"
CORSA = FIXTURES / "opel_corsa_cenik.pdf"
ASTRA = FIXTURES / "opel_astra_hb_cenik.pdf"


def _equipment_by_trim(variants, model: str) -> dict:
    return {v.trim: v.equipment for v in variants if v.model == model}


def test_corsa_equipment_counts_increase_with_trim_level() -> None:
    variants = OpelParser().parse(CORSA)
    by_trim = _equipment_by_trim(variants, "Corsa")
    counts = [len(by_trim[t]) for t in ("Edition", "YES", "GS")]
    assert counts == [50, 70, 68]
    assert all(v == "STANDARD" for v in by_trim["Edition"].values())


def test_corsa_equipment_has_real_item_names_from_both_columns() -> None:
    # Two bullets share one physical text line (left/right column) - both
    # must come out as separate items, not merged into one.
    variants = OpelParser().parse(CORSA)
    by_trim = _equipment_by_trim(variants, "Corsa")
    assert "Elektronický stabilizační systém ESP" in by_trim["Edition"]
    assert "Komfortní sedadla, látkové čalounění Fresez" in by_trim["Edition"]
    assert "Asistent pro rozjezd do kopce" in by_trim["Edition"]


def test_astra_equipment_has_real_item_names() -> None:
    variants = OpelParser().parse(ASTRA)
    by_trim = _equipment_by_trim(variants, "Astra")
    assert "Automatická jednozónová klimatizace" in by_trim["Edition"]
    assert len(by_trim["Ultimate"]) == 96


def test_opel_parser_attaches_equipment_to_variants() -> None:
    variants = OpelParser().parse(CORSA)
    yes_trim = next(v for v in variants if v.trim == "YES")
    assert len(yes_trim.equipment) == 70
    assert not yes_trim.equipment_surcharge  # no priced options on this page

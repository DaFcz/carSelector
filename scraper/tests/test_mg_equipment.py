"""Tests for mg_equipment.parse_equipment against the real fixtures
test_mg_parser.py uses, plus MgParser's own wiring of the result onto
ExtractedVariant.equipment.

Item counts/names were cross-checked by hand against the fixtures' own
two-page VÝBAVA matrix - see mg_equipment.py's module docstring for why
the mark glyphs ("•"/"—") are still read per-page from each page's own
legend line rather than hardcoded, and why MG HS's own equipment pages
come back empty (a real source gap, not a parser bug)."""
from pathlib import Path

from scraper.parsers.mg import MgParser

FIXTURES = Path(__file__).parent / "fixtures"
ZS = FIXTURES / "mg_zs_cenik.pdf"
MG3 = FIXTURES / "mg_mg3_cenik.pdf"
HS = FIXTURES / "mg_hs_cenik.pdf"


def _equipment_by_trim(variants, model: str) -> dict:
    return {v.trim: v.equipment for v in variants if v.model == model}


def test_zs_equipment_counts_increase_with_trim_level() -> None:
    variants = MgParser().parse(ZS)
    by_trim = _equipment_by_trim(variants, "ZS")
    counts = [len(by_trim[t]) for t in ("Excite", "Essential", "Emotion", "Elegance", "Exclusive")]
    assert counts == [41, 42, 47, 47, 50]
    assert all(v == "STANDARD" for v in by_trim["Exclusive"].values())


def test_zs_equipment_has_real_item_names() -> None:
    variants = MgParser().parse(ZS)
    by_trim = _equipment_by_trim(variants, "ZS")
    assert "Systém nouzového volání E-Call" in by_trim["Excite"]
    assert "Systém monitorování tlaku v pneumatikách (TPMS)" in by_trim["Excite"]


def test_mg3_equipment_has_real_item_names() -> None:
    variants = MgParser().parse(MG3)
    by_trim = _equipment_by_trim(variants, "3")
    assert "Alarm - elektronické zabezpečení, elektronický imobilizér" in by_trim["Excite"]
    assert "Systém ISOFIX na zadních sedadlech" in by_trim["Excite"]


def test_hs_has_no_equipment_pages() -> None:
    # Real source gap: MG HS's fixture has no VÝBAVA matrix pages at all,
    # verified by hand - every trim legitimately comes back empty rather
    # than guessed at.
    variants = MgParser().parse(HS)
    assert variants
    assert all(v.equipment == {} for v in variants)


def test_mg_parser_attaches_equipment_to_variants() -> None:
    variants = MgParser().parse(ZS)
    essential = next(v for v in variants if v.trim == "Essential")
    assert len(essential.equipment) == 42
    assert not essential.equipment_surcharge  # no priced options on this matrix

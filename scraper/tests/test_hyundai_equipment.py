"""Tests for hyundai_equipment.parse_equipment against the real fixtures
test_hyundai_parser.py uses, plus HyundaiParser's own wiring of the result
onto ExtractedVariant.equipment.

Item counts and names were cross-checked by hand against the fixtures'
own availability-matrix pages - see hyundai_equipment.py's module
docstring for why marks are read from the right end of each row rather
than the first, and how package-only cells (e.g. Santa Fe's "PREMIUM")
fall out of the row-validation naturally rather than needing their own
vocabulary."""
from pathlib import Path

from scraper.parsers.hyundai import HyundaiParser

FIXTURES = Path(__file__).parent / "fixtures"
I20 = FIXTURES / "hyundai_i20_cenik.pdf"
KONA = FIXTURES / "hyundai_kona_cenik.pdf"


def _equipment_by_trim(variants, model: str) -> dict:
    return {v.trim: v.equipment for v in variants if v.model == model}


def test_i20_equipment_counts_increase_with_trim_level() -> None:
    variants = HyundaiParser().parse(I20)
    by_trim = _equipment_by_trim(variants, "i20")
    counts = [len(by_trim[t]) for t in ("START", "COMFORT", "SMART", "STYLE")]
    assert counts == [69, 71, 80, 84]
    assert all(v == "STANDARD" for v in by_trim["STYLE"].values())


def test_i20_equipment_has_real_item_names() -> None:
    variants = HyundaiParser().parse(I20)
    by_trim = _equipment_by_trim(variants, "i20")
    assert "Halogenové reflektorové přední světlomety" in by_trim["START"]
    # Trailing-mark-run parsing must not misfire on a mid-phrase dash.
    assert "Bi-LED reflektorové přední světlomety se statickým přisvěcováním do zatáčky" in by_trim["SMART"]


def test_kona_equipment_skips_package_only_trim() -> None:
    # "COMFORT CLUB" cells hold a package name ("PREMIUM"/"CLUB"...)
    # instead of a mark in this fixture's own matrix - the row's mark run
    # comes out short and the whole row is skipped rather than guessed at,
    # so this trim legitimately ends up with zero items.
    variants = HyundaiParser().parse(KONA)
    by_trim = _equipment_by_trim(variants, "Kona")
    assert by_trim["COMFORT CLUB"] == {}
    assert len(by_trim["COMFORT"]) == 70
    assert len(by_trim["STYLE"]) == 77


def test_hyundai_parser_attaches_equipment_to_variants() -> None:
    variants = HyundaiParser().parse(I20)
    comfort = next(v for v in variants if v.trim == "COMFORT")
    assert len(comfort.equipment) == 71
    assert not comfort.equipment_surcharge  # no priced options on this matrix

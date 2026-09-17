"""Tests for peugeot_equipment.parse_equipment against real fixtures,
plus PeugeotParser's own wiring of the result onto ExtractedVariant.
equipment/equipment_surcharge.

This is the brand a real user reported ("Peugeot 208 GT has no equipment
shown") - test_208_gt_has_real_equipment below is that exact regression
case. Item names/prices were cross-checked by hand against
peugeot_208_cenik.pdf's own "VÝBAVA PEUGEOT 208" pages - see
peugeot_equipment.py's module docstring for the Private-Use-Area ""
mark, the hybrid mark/price cells, and the known limitation where a run of
unusually tightly-spaced items can merge into one paragraph."""
from pathlib import Path

from scraper.parsers.peugeot import PeugeotParser

FIXTURES = Path(__file__).parent / "fixtures"
P208 = FIXTURES / "peugeot_208_cenik.pdf"
P2008 = FIXTURES / "peugeot_2008_cenik.pdf"


def _equipment_by_trim(variants, model: str) -> dict:
    return {v.trim: v for v in variants if v.model == model}


def test_208_gt_has_real_equipment() -> None:
    # The reported case: Peugeot 208 GT previously had zero equipment.
    by_trim = _equipment_by_trim(PeugeotParser().parse(P208), "208")
    gt = by_trim["GT"]
    assert len(gt.equipment) >= 70
    assert gt.equipment["ESP + ASR + Pomoc při rozjezdu do svahu"] == "STANDARD"
    assert gt.equipment["Elektrický posilovač řízení"] == "STANDARD"


def test_208_equipment_counts_increase_with_trim_level() -> None:
    by_trim = _equipment_by_trim(PeugeotParser().parse(P208), "208")
    counts = {t: len(by_trim[t].equipment) for t in ("STYLE", "EDITION", "BUSINESS", "ALLURE", "GT")}
    assert counts["STYLE"] < counts["GT"]
    assert all(c > 0 for c in counts.values())


def test_208_captures_real_priced_options() -> None:
    # Hybrid cells: some trims get a real Kč price instead of a plain
    # included/unavailable mark - a genuine OPTIONAL item, not "everything
    # non-included is unavailable".
    by_trim = _equipment_by_trim(PeugeotParser().parse(P208), "208")
    gt = by_trim["GT"]
    assert gt.equipment.get("Pack Vision: Visiopark 2 (couvací a přední kamera 360°) Systém sledování mrtvého úhlu Vnější zpětná zrcátka s bočním osvětlením karoserie") == "OPTIONAL"
    assert gt.equipment_surcharge.get(
        "Pack Vision: Visiopark 2 (couvací a přední kamera 360°) Systém sledování mrtvého úhlu Vnější zpětná zrcátka s bočním osvětlením karoserie"
    ) == 8000.0


def test_2008_equipment_has_real_item_names() -> None:
    by_trim = _equipment_by_trim(PeugeotParser().parse(P2008), "2008")
    assert by_trim
    any_trim = next(iter(by_trim.values()))
    assert any_trim.equipment
    assert all(name.strip() for name in any_trim.equipment)

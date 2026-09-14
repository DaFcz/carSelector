"""Tests for mazda_equipment.parse_equipment against the same three real
fixtures test_mazda_parser.py uses (mazda_cx-5_cenik.pdf, mazda_cx-30
_cenik.pdf, mazda3_cenik.pdf), plus MazdaParser's own wiring of the result
onto ExtractedVariant.equipment.

Item counts were cross-checked by hand against each fixture's own VÝBAVA
tables - see mazda_equipment.py's module docstring for why the three
fixtures need three different mark alphabets (plain letters, PDF CIDs, and
Private-Use-Area glyphs) reconciled through each page's own legend line
rather than one hardcoded set of marks."""
from pathlib import Path

from scraper.parsers.mazda import MazdaParser

FIXTURES = Path(__file__).parent / "fixtures"
CX5 = FIXTURES / "mazda_cx-5_cenik.pdf"
CX30 = FIXTURES / "mazda_cx-30_cenik.pdf"
MAZDA3 = FIXTURES / "mazda3_cenik.pdf"


def _equipment_by_trim(variants, model: str) -> dict:
    return {v.trim: v.equipment for v in variants if v.model == model}


def test_cx5_equipment_counts_increase_with_trim_level() -> None:
    # Higher trims strictly add equipment on top of lower ones for CX-5
    # (verified by hand against the brochure's own VÝBAVA tables) - unlike
    # Dacia, a higher Mazda trim's set isn't guaranteed to be a superset
    # (a few items are Prime-Line-only, e.g. the base 17" wheel design),
    # but the total COUNT climbs monotonically Prime -> Centre -> Exclusive
    # -> Homura.
    variants = MazdaParser().parse(CX5)
    by_trim = _equipment_by_trim(variants, "CX-5")
    counts = [len(by_trim[t]) for t in ("Prime-Line", "Centre-Line", "Exclusive-Line", "Homura")]
    assert counts == [73, 90, 94, 104]
    assert all(v == "STANDARD" for v in by_trim["Homura"].values())


def test_cx5_equipment_has_real_item_names() -> None:
    variants = MazdaParser().parse(CX5)
    by_trim = _equipment_by_trim(variants, "CX-5")
    assert "Elektrická parkovací brzda (EPB) + Auto Hold s HDP" in by_trim["Prime-Line"]
    assert "Integrovaný Google" in by_trim["Prime-Line"]  # standard on every CX-5 trim
    # 17" wheels only on Prime-Line - the exact per-trim (not just per-count) check.
    assert "17” lité disky kol – Grey Metallic (225/65R17)" in by_trim["Prime-Line"]
    assert "17” lité disky kol – Grey Metallic (225/65R17)" not in by_trim["Homura"]


def test_cx5_equipment_handles_mid_item_wrapped_marks_row() -> None:
    # "Pokročilý protikolizní systém (přední a zadní)" wraps across several
    # "- <sub-feature>" bullet lines with its own "l l l l" mark line
    # landing in the middle of that block, not at the end - see module
    # docstring. Must still come through as one whole item, standard on
    # every trim.
    variants = MazdaParser().parse(CX5)
    by_trim = _equipment_by_trim(variants, "CX-5")
    name = "Pokročilý protikolizní systém (přední a zadní) - Asistent pro zamezení čelnímu střetu při odbočování vlevo - Zmírnění následků čelního střetu - Asistent brzdění při vyjíždění z křižovatky (FCTB) - Funkce detekce překážky při parkování - Asistent brzdění při couvání z parkovacího místa (RCTB)"
    for trim in ("Prime-Line", "Centre-Line", "Exclusive-Line", "Homura"):
        assert by_trim[trim].get(name) == "STANDARD"
    # The very next item on the same page must be its own separate entry,
    # not merged into the wrapped item above.
    assert by_trim["Prime-Line"].get("Systém upozornění na pohyb před vozem (FCTA)") == "STANDARD"


def test_cx30_equipment_uses_cid_encoded_marks() -> None:
    # CX-30's fixture embeds the standard/optional marks as PDF CIDs with
    # no ToUnicode mapping ("(cid:122)"/"(cid:129)") instead of plain
    # letters - this must still parse correctly by reading the legend.
    variants = MazdaParser().parse(CX30)
    by_trim = _equipment_by_trim(variants, "CX-30")
    assert set(by_trim) == {"Prime-line", "Centre-line", "Exclusive-line", "Takumi", "Homura", "Nagisa"}
    assert all(len(items) > 0 for items in by_trim.values())
    assert "Adaptivní LED světlomety" in by_trim["Takumi"]


def test_mazda3_equipment_covers_hatchback_and_sedan_separately() -> None:
    # Mazda3's fixture uses Private-Use-Area icon-font glyphs for its
    # marks, has a genuine two-word trim ("Homura Plus") in its Hatchback
    # header, and splits Hatchback/Sedan into separate VÝBAVA pages with
    # different trim ladders (Sedan has no Homura/Homura Plus/Nagisa).
    variants = MazdaParser().parse(MAZDA3)
    hatchback = _equipment_by_trim([v for v in variants if v.model == "3"], "3")
    sedan = _equipment_by_trim([v for v in variants if v.model == "3 Sedan"], "3 Sedan")

    assert set(hatchback) == {
        "Prime-line", "Centre-line", "Exclusive-line", "Takumi", "Homura", "Homura Plus", "Nagisa"
    }
    assert set(sedan) == {"Prime-line", "Centre-line", "Exclusive-line", "Takumi"}
    # "Homura Plus" must be its own trim, not merged with plain "Homura".
    assert hatchback["Homura"] != hatchback["Homura Plus"]
    assert all(len(items) > 0 for items in hatchback.values())
    assert all(len(items) > 0 for items in sedan.values())

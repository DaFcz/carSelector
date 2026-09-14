"""Tests for renault_equipment.parse_standard_equipment against real
fixtures (renault_captur_cenik.pdf, renault_arkana_cenik.pdf,
renault_espace_cenik.pdf, renault_clio_cenik.pdf, renault_austral_cenik.pdf
- see scraper/tests/fixtures/), plus RenaultParser's own wiring of the
result onto ExtractedVariant.equipment.

Item names/counts were transcribed by hand from each fixture's own
`page.extract_text()` output for its "hlavní prvky sériové výbavy" page -
see renault_equipment.py's module docstring for the delta-resolution
("navíc oproti <trim>") logic these counts exercise, and for why Austral's
own two-side-by-side-columns layout is expected to yield nothing here."""
from pathlib import Path

from scraper.parsers.renault import RenaultParser
from scraper.parsers.renault_equipment import parse_standard_equipment
import pdfplumber

FIXTURES = Path(__file__).parent / "fixtures"
CAPTUR = FIXTURES / "renault_captur_cenik.pdf"
ARKANA = FIXTURES / "renault_arkana_cenik.pdf"
ESPACE = FIXTURES / "renault_espace_cenik.pdf"
CLIO = FIXTURES / "renault_clio_cenik.pdf"
AUSTRAL = FIXTURES / "renault_austral_cenik.pdf"


def _equipment_by_trim(variants, model: str) -> dict:
    return {v.trim: v.equipment for v in variants if v.model == model}


def test_captur_equipment_counts_and_delta_chain() -> None:
    # Evolution has its own standalone 13-item list; Techno and Esprit
    # Alpine are each declared "navíc oproti <previous trim>", so their own
    # new items (13, then 8) fold onto the previous trim's already-resolved
    # total - counts transcribed by hand from page 3's own bullet list.
    with pdfplumber.open(CAPTUR) as pdf:
        result = parse_standard_equipment(pdf)

    assert set(result) == {"Evolution", "Techno", "Esprit Alpine"}
    assert len(result["Evolution"]) == 13
    assert len(result["Techno"]) == 26
    assert len(result["Esprit Alpine"]) == 34

    assert result["Evolution"]["manuální klimatizace"] == "STANDARD"
    assert result["Evolution"]["full led přední světlomety"] == "STANDARD"
    # Techno's own new item plus Evolution's base item, both present.
    assert result["Techno"]["automatická klimatizace"] == "STANDARD"
    assert result["Techno"]["manuální klimatizace"] == "STANDARD"
    # Esprit Alpine's own new item plus the full inherited chain.
    assert result["Esprit Alpine"]["indukční nabíječka pro smartphone"] == "STANDARD"
    assert result["Esprit Alpine"]["full led přední světlomety"] == "STANDARD"
    assert result["Esprit Alpine"]["automatická klimatizace"] == "STANDARD"


def test_arkana_equipment_two_trims() -> None:
    # Arkana's fixture only has two trims: Techno (standalone 11-item list)
    # and Esprit Alpine (navíc oproti Techno, 8 new items -> 19 total).
    with pdfplumber.open(ARKANA) as pdf:
        result = parse_standard_equipment(pdf)

    assert set(result) == {"Techno", "Esprit Alpine"}
    assert len(result["Techno"]) == 11
    assert len(result["Esprit Alpine"]) == 19
    assert result["Techno"]["full LED přední světlomety"] == "STANDARD"
    assert result["Esprit Alpine"]["vyhřívaný volant"] == "STANDARD"
    assert result["Esprit Alpine"]["černý metalický lak"] == "STANDARD"


def test_espace_equipment_resolves_sibling_deltas_not_a_chain() -> None:
    # Espace's page 3 declares BOTH "Esprit Alpine" and "Iconic" as "navíc
    # oproti Techno" (not "navíc oproti Esprit Alpine" for Iconic) - two
    # sibling trims built on the same Techno base, not a linear chain. A
    # naive "carry forward one running accumulator" approach (Dacia's own,
    # which only ever sees true chains) would incorrectly leak Esprit
    # Alpine's own items into Iconic's list.
    with pdfplumber.open(ESPACE) as pdf:
        result = parse_standard_equipment(pdf)

    assert set(result) == {"Techno", "Esprit Alpine", "Iconic"}
    assert len(result["Techno"]) == 13
    assert len(result["Esprit Alpine"]) == 22  # 13 base + 9 own
    assert len(result["Iconic"]) == 22  # 13 base + 9 own - NOT 13 + 9 + 9

    # Esprit Alpine-only items must never appear on Iconic, and vice versa.
    assert "hliníkové pedály" in result["Esprit Alpine"]
    assert "hliníkové pedály" not in result["Iconic"]
    assert "360° kamerový systém" in result["Iconic"]
    assert "360° kamerový systém" not in result["Esprit Alpine"]
    # Both trims still carry the shared Techno base.
    assert "systém multi-sense" in result["Esprit Alpine"]
    assert "systém multi-sense" in result["Iconic"]


def test_clio_equipment_handles_bullet_on_its_own_line() -> None:
    # Clio's own PDF puts the "•" character alone on its own line, with the
    # item's text only starting on the following line(s) - a different
    # physical row shape from every other single-column fixture, but the
    # same state machine handles it without special-casing since an item's
    # name is just whatever text accumulates between two bullet markers.
    with pdfplumber.open(CLIO) as pdf:
        result = parse_standard_equipment(pdf)

    assert set(result) == {"Evolution", "Techno", "Esprit Alpine"}
    assert len(result["Evolution"]) == 13
    assert len(result["Techno"]) == 25
    assert len(result["Esprit Alpine"]) == 35
    assert result["Evolution"]["full LED světlomety"] == "STANDARD"
    assert result["Evolution"]["hlavové airbagy pro první a druhou řadu sedadel"] == "STANDARD"


def test_austral_two_column_layout_is_skipped_not_guessed() -> None:
    # Austral's own page 3 renders standard equipment as two side-by-side
    # columns ("• full LED světlomety LED pure vision • speciální
    # metalický lak bílá nacré" - two "•"-led items on one physical line) -
    # this module bails out entirely rather than guess how to split such a
    # line into two separate item names.
    with pdfplumber.open(AUSTRAL) as pdf:
        result = parse_standard_equipment(pdf)

    assert result == {}


def test_renault_parser_wires_equipment_onto_variants() -> None:
    variants = RenaultParser().parse(CAPTUR)
    by_trim = _equipment_by_trim(variants, "Captur")

    assert by_trim  # at least one Captur variant carries equipment
    for trim, equipment in by_trim.items():
        assert equipment, f"{trim} variant should have non-empty equipment"
        assert all(status == "STANDARD" for status in equipment.values())
    assert len(by_trim["Evolution"]) == 13
    assert len(by_trim["Esprit Alpine"]) == 34


def test_renault_parser_variant_count_unaffected_by_equipment_wiring() -> None:
    # Austral's equipment section is skipped entirely (two-column layout),
    # but its own price-table extraction must be completely unaffected -
    # every variant still comes through, just with an empty equipment dict.
    variants = RenaultParser().parse(AUSTRAL)
    assert len(variants) > 0
    assert all(v.equipment == {} for v in variants)

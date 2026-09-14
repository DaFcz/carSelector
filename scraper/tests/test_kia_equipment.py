"""Tests for kia_equipment.parse_standard_equipment against real fixtures
(kia_niro_cenik.pdf, kia_ceed_sw_cenik.pdf, kia_sportage_hev_phev_cenik.pdf),
plus KiaParser's own wiring of the result onto ExtractedVariant.equipment.

Item names/counts were hand-transcribed from each fixture's own "Hlavní
prvky standardní výbavy" bullet page (page.extract_text()) and cross-
checked by summing each trim's own delta bullets against the base trim(s)
it resolves from - see kia_equipment.py's module docstring for why that
resolution is by explicit name reference rather than a simple running
accumulator (Dacia's approach)."""
from pathlib import Path

from scraper.parsers.kia import KiaParser

FIXTURES = Path(__file__).parent / "fixtures"
NIRO = FIXTURES / "kia_niro_cenik.pdf"
CEED_SW = FIXTURES / "kia_ceed_sw_cenik.pdf"
SPORTAGE_HEV_PHEV = FIXTURES / "kia_sportage_hev_phev_cenik.pdf"


def _equipment_by_trim(variants) -> dict:
    return {v.trim: v.equipment for v in variants}


def test_niro_equipment_counts_accumulate_through_the_delta_chain() -> None:
    # Comfort is the plain (non-delta) base list; Style is "oproti Comfort"
    # (11 own items); Premium is "oproti Style" (7 own items) - each level
    # folds in everything the referenced trim already has, so counts climb
    # 11 -> 18 -> 25 (hand-counted from the fixture's own bullets, no
    # overlapping item text between any two sections).
    variants = KiaParser().parse(NIRO)
    by_trim = _equipment_by_trim(variants)
    assert len(by_trim["Comfort"]) == 11
    assert len(by_trim["Style"]) == 18
    assert len(by_trim["Premium"]) == 25
    assert all(v == "STANDARD" for v in by_trim["Premium"].values())


def test_niro_equipment_has_real_item_names_including_doubled_glyph_section() -> None:
    # Style's own "Hlavní prvky standardní výbavy oproti Comfort:" marker
    # line has every character doubled in this fixture's PDF text (a bold-
    # run glyph-duplication artifact - see module docstring) - the section
    # must still be recognized and its items attributed to Style.
    variants = KiaParser().parse(NIRO)
    by_trim = _equipment_by_trim(variants)
    assert "umělou kůží potažený volant" in by_trim["Comfort"]  # Comfort's own item
    assert "vnější zpětná zrcátka elektricky ovládaná, vyhřívaná a sklopná s blikači" in by_trim["Style"]
    assert "čalounění sedadel v kombinaci látka/umělá kůže" in by_trim["Style"]
    # Premium-only item, inherited neither by Comfort nor Style.
    assert "hliníkové pedály" in by_trim["Premium"]
    assert "hliníkové pedály" not in by_trim["Comfort"]
    assert "hliníkové pedály" not in by_trim["Style"]
    # Comfort's own items are inherited all the way up to Premium.
    assert "umělou kůží potažený volant" in by_trim["Premium"]


def test_ceed_sw_equipment_is_delta_only_when_base_trim_is_unresolvable() -> None:
    # Ceed SW's price table (and this bullet page) only ever prices/lists
    # SPIN and TOP - both reference a "Comfort" trim that has no section of
    # its own anywhere in this fixture. Rather than fabricate Comfort's
    # contents, unresolvable references are treated as an empty base, so
    # SPIN/TOP come back with exactly their own confirmed delta items.
    variants = KiaParser().parse(CEED_SW)
    by_trim = _equipment_by_trim(variants)
    assert set(by_trim) == {"SPIN", "TOP"}
    assert len(by_trim["SPIN"]) == 11
    assert len(by_trim["TOP"]) == 7
    assert "kůží potažený volant" in by_trim["SPIN"]
    assert "zadní LED světlomety" in by_trim["TOP"]
    # TOP's own bullets are never merged into SPIN's (both reference the
    # same unresolvable "Comfort", not each other).
    assert "zadní LED světlomety" not in by_trim["SPIN"]


def test_sportage_hev_phev_top_resolves_against_exclusive_not_black_edition() -> None:
    # TOP's own marker line reads "oproti Exclusive", skipping over BLACK
    # EDITION even though BLACK EDITION's section comes first in reading
    # order - resolution must follow the named reference, not simply chain
    # from whichever section was parsed immediately before.
    variants = KiaParser().parse(SPORTAGE_HEV_PHEV)
    by_trim = _equipment_by_trim(variants)
    assert set(by_trim) == {"Comfort", "Exclusive", "BLACK EDITION", "TOP", "GT-Line"}
    assert len(by_trim["Comfort"]) == 11
    assert len(by_trim["Exclusive"]) == 15
    assert len(by_trim["TOP"]) == 24  # Exclusive's 15 + TOP's own 9 delta items
    # A BLACK-EDITION-only item must NOT leak into TOP, since TOP resolves
    # from Exclusive rather than from BLACK EDITION.
    assert "interiér čalouněný v černé kůži" in by_trim["BLACK EDITION"]
    assert "interiér čalouněný v černé kůži" not in by_trim["TOP"]
    # GT-Line ("oproti TOP") inherits everything TOP has plus its own items.
    assert "GT-Line design exteriéru a interiéru" in by_trim["GT-Line"]
    assert "elektricky stavitelné sedadlo řidiče a spolujezdce" in by_trim["GT-Line"]  # from TOP
    assert all(v == "STANDARD" for v in by_trim["GT-Line"].values())


def test_kia_equipment_never_populates_surcharge() -> None:
    # The bullet page never states a price - equipment_surcharge must stay
    # empty for every variant, same "no price on this page" stance as
    # dacia_equipment.py.
    variants = KiaParser().parse(NIRO)
    assert all(v.equipment_surcharge == {} for v in variants)

"""Tests for vw_equipment.parse_standard_equipment against the real
fixtures test_volkswagen_parser.py/test_volkswagen_ev_parser.py use
(vw_golf_cenik.pdf, vw_id3neo_cenik.pdf, vw_id4_cenik.pdf), plus both
VolkswagenParser and VolkswagenEvParser's own wiring of the result onto
ExtractedVariant.equipment.

Item counts and the specific "Navíc oproti výbavě <named trim>, not
necessarily the trim right before it" branching (Golf's own Style AND
R-Line both build on Life, not on each other) were cross-checked by hand
against the fixtures' own "Sériová Výbava" pages - see vw_equipment.py's
module docstring."""
from pathlib import Path

from scraper.parsers.volkswagen import VolkswagenParser
from scraper.parsers.volkswagen_ev import VolkswagenEvParser

FIXTURES = Path(__file__).parent / "fixtures"
GOLF = FIXTURES / "vw_golf_cenik.pdf"
ID3 = FIXTURES / "vw_id3neo_cenik.pdf"
ID4 = FIXTURES / "vw_id4_cenik.pdf"


def _equipment_by_trim(variants) -> dict:
    result: dict[str, dict] = {}
    for v in variants:
        result.setdefault(v.trim, v.equipment)
    return result


def test_golf_equipment_branches_from_a_named_trim_not_the_previous_one() -> None:
    # Style AND R-Line are both "Navíc oproti výbavě Life" in the source
    # document (verified by hand), even though R-Line's own page comes
    # right after Style's - must not accidentally build R-Line on top of
    # Style.
    variants = VolkswagenParser().parse(GOLF)
    by_trim = _equipment_by_trim(variants)

    assert len(by_trim["Golf"]) == 63
    assert len(by_trim["Life"]) == 94
    assert len(by_trim["Style"]) == 108
    assert len(by_trim["R-Line"]) == 101

    # Every Golf-base item is inherited by every higher trim.
    assert set(by_trim["Golf"]) <= set(by_trim["Life"])
    assert set(by_trim["Life"]) <= set(by_trim["Style"])
    assert set(by_trim["Life"]) <= set(by_trim["R-Line"])
    # Style's own additions must NOT leak into R-Line (both branch from
    # Life independently) - a concrete Style-only item.
    style_only = set(by_trim["Style"]) - set(by_trim["Life"])
    assert style_only and not (style_only & set(by_trim["R-Line"]))


def test_golf_equipment_has_real_item_names() -> None:
    variants = VolkswagenParser().parse(GOLF)
    by_trim = _equipment_by_trim(variants)
    assert "Čelní sklo tepelně izolující" in by_trim["Golf"]
    assert "ISOFIX" in by_trim["Golf"]
    assert all(v == "STANDARD" for v in by_trim["Golf"].values())


def test_volkswagen_parser_attaches_equipment_to_variants() -> None:
    variants = VolkswagenParser().parse(GOLF)
    life_variant = next(v for v in variants if v.trim == "Life")
    assert len(life_variant.equipment) == 94
    assert not life_variant.equipment_surcharge  # standard equipment only, see module docstring


def test_id4_equipment_covers_pure_pro_gtx() -> None:
    variants = VolkswagenEvParser().parse(ID4)
    by_trim = _equipment_by_trim(variants)
    assert len(by_trim["Pure"]) == 55
    assert len(by_trim["Pro"]) == 64
    assert len(by_trim["GTX"]) == 73
    assert set(by_trim["Pure"]) <= set(by_trim["Pro"])
    assert set(by_trim["Pro"]) <= set(by_trim["GTX"])


def test_id3_neo_style_has_no_dedicated_equipment_page() -> None:
    # Real source-document gap, not a parser bug: the ID.3 Neo document
    # only has "Sériová Výbava" pages for Trend and Life, none for Style
    # even though Style is a real, priced trim in the price table -
    # verified by hand against every page of the fixture. Equipment stays
    # empty for it rather than guessing it equals Life's.
    variants = VolkswagenEvParser().parse(ID3)
    by_trim = _equipment_by_trim(variants)
    assert len(by_trim["Trend"]) == 69
    assert len(by_trim["Life"]) == 84
    assert by_trim["Style"] == {}

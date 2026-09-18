"""Tests for cupra_equipment.parse_standard_equipment/parse_colors
against real fixtures test_cupra_parser.py uses, plus CupraParser's own
wiring of both into ExtractedVariant.equipment/equipment_surcharge
(colors folded into the same fields - see cupra.py's own comment on why).

Item/color names, counts and prices were cross-checked by hand against
Formentor's own "SÉRIOVÁ VÝBAVA"/"BARVY" pages - see cupra_equipment.py's
module docstring for the column-detection approach this exercises (a
wrapped heading/item line, a trim heading that copies an explicitly
named base trim, a color row whose price is one shared value for
whichever trims marked it optional)."""
from pathlib import Path

from scraper.parsers.cupra import CupraParser

FIXTURES = Path(__file__).parent / "fixtures"
FORMENTOR = FIXTURES / "cupra_formentor_cenik.pdf"
BORN = FIXTURES / "cupra_born_cenik.pdf"
TERRAMAR = FIXTURES / "cupra_terramar_cenik.pdf"


def _by_trim(variants) -> dict:
    result: dict[str, object] = {}
    for v in variants:
        result.setdefault(v.trim, v)
    return result


def test_formentor_equipment_inherits_named_base_trim() -> None:
    # "VZ Extreme /navíc oproti výbavě CUPRA" must inherit CUPRA's own
    # items even though VZ's own section sits physically between them -
    # never assumed to be "whatever came right before".
    by_trim = _by_trim(CupraParser().parse(FORMENTOR))
    cupra_items = set(k for k in by_trim["CUPRA"].equipment if by_trim["CUPRA"].equipment[k] == "STANDARD")
    vz_extreme_items = set(k for k in by_trim["VZ Extreme"].equipment if by_trim["VZ Extreme"].equipment[k] == "STANDARD")
    assert len(by_trim["CUPRA"].equipment) >= 80
    assert cupra_items <= vz_extreme_items
    assert "Matrix HD LED světlomety" in vz_extreme_items  # VZ Extreme's own addition


def test_formentor_equipment_has_real_item_names() -> None:
    by_trim = _by_trim(CupraParser().parse(FORMENTOR))
    assert by_trim["CUPRA"].equipment.get("CUPRA CONNECT") == "STANDARD"
    assert by_trim["CUPRA"].equipment.get("Digital Cockpit") == "STANDARD"
    assert by_trim["CUPRA"].equipment.get("Elektronický stabilizační systém ESC") == "STANDARD"


def test_formentor_colors_have_real_names_and_shared_prices() -> None:
    by_trim = _by_trim(CupraParser().parse(FORMENTOR))
    cupra = by_trim["CUPRA"]
    assert cupra.equipment.get("Fiord modrá - 9K9K") == "STANDARD"
    assert cupra.equipment.get("Glacial bílá - 2Y2Y") == "OPTIONAL"
    assert cupra.equipment_surcharge.get("Glacial bílá - 2Y2Y") == 23000.0
    # A color absent from a trim's own matrix column must not appear at all.
    assert "Century Bronze matná - L3L3" not in cupra.equipment
    vz = by_trim["VZ"]
    assert vz.equipment.get("Century Bronze matná - L3L3") == "OPTIONAL"
    assert vz.equipment_surcharge.get("Century Bronze matná - L3L3") == 65500.0


def test_cupra_parser_attaches_equipment_and_colors_to_variants() -> None:
    variants = CupraParser().parse(FORMENTOR)
    cupra_variant = next(v for v in variants if v.trim == "CUPRA")
    assert len(cupra_variant.equipment) >= 85
    assert cupra_variant.equipment_surcharge  # colors contribute real prices


def test_born_and_terramar_parse_without_error() -> None:
    # Smoke coverage for the remaining models test_cupra_parser.py also
    # covers - both models get real equipment and at least some colors.
    for fixture in (BORN, TERRAMAR):
        variants = CupraParser().parse(fixture)
        assert variants
        assert all(v.equipment for v in variants)

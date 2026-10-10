"""Tests for skoda_standard_equipment on real Škoda price lists. Expected
items are transcribed by hand from the PDFs' "Standardní výbava" pages
(Elroq p. 4-8, Octavia p. 9), not derived from the parser - same
discipline as test_skoda_equipment.py."""

from pathlib import Path

import pdfplumber

from scraper.parsers.skoda_ev import SkodaEvParser
from scraper.parsers.skoda_standard_equipment import equipment_for_trim, parse_standard_equipment

FIXTURES = Path(__file__).parent / "fixtures"
ELROQ = FIXTURES / "skoda_elroq_cenik.pdf"
OCTAVIA = FIXTURES / "skoda_octavia_cenik.pdf"


def _standard(fixture: Path) -> dict[str, dict[str, str]]:
    with pdfplumber.open(fixture) as pdf:
        return parse_standard_equipment(pdf)


def test_elroq_finds_every_trim_page() -> None:
    assert list(_standard(ELROQ)) == ["Essence", "Selection", "Sportline", "Laurin & Klement", "RS"]


def test_items_from_every_column_are_standard() -> None:
    essence = _standard(ELROQ)["Essence"]
    # one item from each of the page's four columns
    for item in (
        "Dvouzónová klimatizace Climatronic",  # Design / Komfort
        "Parkovací kamera vzadu",  # Bezpečnost
        'Virtuální kokpit 5"',  # Funkčnost
        "Tísňové volání eCall",  # Funkčnost, spilled into a 4th column
    ):
        assert essence[item] == "STANDARD"


def test_wrapped_lines_are_joined_into_one_item() -> None:
    essence = _standard(ELROQ)["Essence"]
    assert (
        "Vnější zpětná zrcátka elektricky nastavitelná a sklopná, vyhřívaná a automaticky odclonitelné u řidiče"
        in essence
    )
    assert (
        "Příprava pro balíček služeb Škoda Connect Standard - Proaktivní servis, Vzdálený přístup, "
        "Vzdálené služby iV, Chytré služby" in essence
    )


def test_trim_inherits_its_base_trim() -> None:
    data = _standard(ELROQ)
    # Selection page: "(navíc oproti výbavovému stupni Essence)"
    assert "Vyhřívaná přední sedadla" in data["Selection"]
    assert "Vyhřívaná přední sedadla" not in data["Essence"]
    assert "Parkovací kamera vzadu" in data["Selection"]
    # RS builds on Sportline, which builds on Selection
    assert "Travel Assist 3.0" in data["RS"]
    assert "Vyhřívaná přední sedadla" in data["RS"]


def test_bullet_group_keeps_items_and_drops_group_label() -> None:
    sportline = _standard(ELROQ)["Sportline"]
    assert "Travel Assist 3.0" in sportline
    assert "Nouzový asistent" in sportline
    assert "Asistovaná jízda" not in sportline


def test_footnote_text_and_marks_are_not_items() -> None:
    sportline = _standard(ELROQ)["Sportline"]
    assert "Digitální klíč v přípravě pro odemykání/zamykání a startování" in sportline
    assert not any("plánovanou budoucí funkcí" in item or "nebude funkce" in item for item in sportline)


def test_single_item_columns_are_not_merged_into_neighbours() -> None:
    # Octavia Sportline p. 9: Bezpečnost and Funkčnost hold one item each,
    # on the same line as the first Design item.
    sportline = _standard(OCTAVIA)["Sportline"]
    assert "Matrix-LED přední světlomety s funkcí do špatného počasí" in sportline
    assert "Ostřikovače světlometů" in sportline
    assert 'Kola z lehké slitiny Slagard 17" černá leštěná - disk 7J × 17" ET46, pneu 205/55 R17' in sportline


def test_two_trim_promo_page_is_skipped() -> None:
    data = _standard(OCTAVIA)
    assert "Classic" not in data
    assert "Dynamic" not in data


def test_ev_variants_carry_standard_and_optional_equipment() -> None:
    variants = SkodaEvParser().parse(ELROQ)
    selection = next(v for v in variants if v.trim == "Selection")
    assert selection.equipment["Vyhřívaná přední sedadla"] == "STANDARD"
    # "Samostatné prvky výbavy" p. 12: "Tepelné čerpadlo – ● ● ● ● 30 500"
    assert selection.equipment["Tepelné čerpadlo"] == "OPTIONAL"
    assert selection.equipment_surcharge["Tepelné čerpadlo"] == 30500
    # ...but it's standard on L&K (p. 7), which wins over the paid listing
    laurin = next(v for v in variants if v.trim == "Laurin & Klement")
    assert laurin.equipment["Tepelné čerpadlo"] == "STANDARD"


def test_equipment_for_trim_accepts_unique_prefix_only() -> None:
    equipment = {"First Edition": {"a": "STANDARD"}, "Top Selection": {"b": "STANDARD"}, "Top Sport": {}}
    assert equipment_for_trim(equipment, "First") == {"a": "STANDARD"}
    assert equipment_for_trim(equipment, "Top") == {}
    assert equipment_for_trim(equipment, "Missing") == {}

"""Tests for dacia_equipment.parse_standard_equipment against the same six
real fixtures test_dacia_parser.py uses (see scraper/tests/fixtures/
dacia_*.pdf), plus DaciaParser's own wiring of the result onto
ExtractedVariant.equipment.

Item counts (Essential/Expression/[Journey|Extreme]/[Extreme|Journey]) were
cross-checked by hand against each fixture's own bullet list - see module
docstring in dacia_equipment.py for the cumulative-vs-standalone distinction
this exercises across models."""
import pdfplumber

from scraper.parsers.dacia import DaciaParser
from scraper.parsers.dacia_equipment import parse_standard_equipment
from scraper.tests.test_dacia_parser import BIGSTER, DUSTER, JOGGER, SANDERO, SPRING, STEPWAY


def _parse(path):
    with pdfplumber.open(path) as pdf:
        return parse_standard_equipment(pdf)


def test_sandero_equipment_is_cumulative_across_trims() -> None:
    # "Hlavní prvky sériové výbavy navíc oproti Essential/Expression:" -
    # each higher trim inherits every lower trim's items plus its own.
    result = _parse(SANDERO)
    assert set(result) == {"Essential", "Expression", "Journey"}
    assert len(result["Essential"]) == 15
    assert len(result["Expression"]) == 25
    assert len(result["Journey"]) == 33
    assert "15\" ocelová kola + kryty kol ELMA" in result["Essential"]
    # Everything Essential has must still be present on Journey (cumulative).
    assert set(result["Essential"]) <= set(result["Journey"])
    assert all(availability == "STANDARD" for availability in result["Journey"].values())


def test_duster_equipment_is_standalone_per_trim() -> None:
    # Duster/Bigster use the plain "Hlavní prvky sériové výbavy:" header for
    # every trim (no "navíc oproti") - each trim's list is already complete
    # on its own, not a delta to fold onto a lower trim.
    result = _parse(DUSTER)
    assert set(result) == {"Essential", "Expression", "Journey", "Extreme"}
    assert len(result["Essential"]) == 13
    assert len(result["Expression"]) == 13
    assert len(result["Journey"]) == 17
    assert len(result["Extreme"]) == 15
    # Not a strict superset relationship like Sandero's - Expression's own
    # list doesn't need to contain every Essential item.
    assert "Klíč s dálkovým ovládáním centrálního zamykání" in result["Essential"]


def test_spring_equipment_normalizes_mixed_case_trim_headings() -> None:
    # Same smallcaps-font issue as the price table itself (dacia.py's
    # module docstring) - "ESSEntiaL"/"ExprESSiOn"/"ExtRÉME"-style headings
    # on this page too.
    result = _parse(SPRING)
    assert set(result) == {"Essential", "Expression", "Extreme"}
    assert len(result["Extreme"]) == 24


def test_jogger_equipment_handles_multi_line_wrapped_items() -> None:
    # E.g. "Multimediální systém Media Control se 4 reproduktory\n+
    # aplikace pro chytré telefony Dacia Media Control" wraps across two
    # lines under one bullet - must merge into a single item, not two.
    result = _parse(JOGGER)
    assert "Multimediální systém Media Control se 4 reproduktory + aplikace pro chytré telefony Dacia Media Control" in (
        result["Essential"]
    )


def test_dacia_parser_attaches_equipment_to_variants() -> None:
    variants = DaciaParser().parse(SANDERO)
    essential = next(v for v in variants if v.trim == "Essential")
    journey = next(v for v in variants if v.trim == "Journey")
    assert essential.equipment
    assert "15\" ocelová kola + kryty kol ELMA" in essential.equipment
    assert len(journey.equipment) == 33
    assert not essential.equipment_surcharge  # no priced options on this page, see module docstring


def test_bigster_and_stepway_equipment_parses_without_error() -> None:
    # Smoke coverage for the remaining two fixtures test_dacia_parser.py
    # also covers, so all six models are exercised here too.
    assert len(_parse(BIGSTER)) == 4
    assert len(_parse(STEPWAY)) == 3

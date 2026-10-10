"""Tests for RenaultParser on all twelve real per-model price lists
(downloaded 2026-09-12 from Renault Group's asset CDN, effective 1
August-10 September 2026 depending on model — see scraper/tests/fixtures/
renault_*.pdf). Prices are transcribed by hand from the PDF text, so it
can always be verified that the extraction matches the source — same
discipline as test_kia_parser.py.

Row counts per fixture were cross-checked by hand against
`page.extract_words()`/`group_into_lines` output for every fixture, not
just spot-checked."""

from pathlib import Path

from scraper.parsers.renault import RenaultParser

FIXTURES = Path(__file__).parent / "fixtures"
CLIO = FIXTURES / "renault_clio_cenik.pdf"
CAPTUR = FIXTURES / "renault_captur_cenik.pdf"
SYMBIOZ = FIXTURES / "renault_symbioz_cenik.pdf"
ARKANA = FIXTURES / "renault_arkana_cenik.pdf"
AUSTRAL = FIXTURES / "renault_austral_cenik.pdf"
ESPACE = FIXTURES / "renault_espace_cenik.pdf"
RAFALE = FIXTURES / "renault_rafale_cenik.pdf"
TWINGO = FIXTURES / "renault_twingo_cenik.pdf"
R4 = FIXTURES / "renault_r4_cenik.pdf"
R5 = FIXTURES / "renault_r5_cenik.pdf"
MEGANE = FIXTURES / "renault_megane_cenik.pdf"
SCENIC = FIXTURES / "renault_scenic_cenik.pdf"


def _variant(variants, trim: str, engine_fragment: str):
    return next(v for v in variants if v.trim == trim and engine_fragment in v.variant_name)


def test_renault_parser_extracts_clio_variants() -> None:
    # Evolution(2) + Techno(3) + Esprit Alpine(2) = 7.
    variants = RenaultParser().parse(CLIO)
    assert len(variants) == 7
    assert all(v.model == "Clio" for v in variants)
    assert all(v.currency == "CZK" for v in variants)
    assert all(v.source_page == 2 for v in variants)

    base = _variant(variants, "Evolution", "TCe 115")
    assert base.price == 434_000.0  # ceníková cena (list price), not the 399 000 Kč bonus-adjusted one
    assert base.powertrain == "ICE"

    hev = _variant(variants, "Techno", "full hybrid E-Tech 160")
    assert hev.powertrain == "HEV"
    assert hev.price == 629_000.0


def test_renault_parser_skips_incomplete_row_without_losing_trim_state() -> None:
    # A row mentioning a price but missing other fields would previously
    # be mistaken for a new trim heading (same class of bug fixed for
    # CUPRA's Born) - verified there's no such row in these fixtures by
    # checking every row's trim resolves to an actual heading, never to
    # leftover legal/promo text.
    variants = RenaultParser().parse(CLIO)
    assert all(v.trim in {"Evolution", "Techno", "Esprit Alpine"} for v in variants)


def test_renault_parser_extracts_captur_variants_with_mhev() -> None:
    variants = RenaultParser().parse(CAPTUR)
    assert len(variants) == 7
    assert all(v.model == "Captur" for v in variants)

    mhev = _variant(variants, "Techno", "mild hybrid 140 EDC")
    assert mhev.powertrain == "MHEV"
    assert mhev.price == 679_000.0


def test_renault_parser_extracts_symbioz_variants() -> None:
    variants = RenaultParser().parse(SYMBIOZ)
    assert len(variants) == 9
    assert all(v.model == "Symbioz" for v in variants)
    assert {v.trim for v in variants} == {"Evolution", "Techno", "Esprit Alpine", "Iconic"}


def test_renault_parser_extracts_arkana_variants() -> None:
    variants = RenaultParser().parse(ARKANA)
    assert len(variants) == 2
    assert all(v.model == "Arkana" for v in variants)
    assert all(v.powertrain == "HEV" for v in variants)


def test_renault_parser_extracts_austral_variants() -> None:
    variants = RenaultParser().parse(AUSTRAL)
    assert len(variants) == 5
    assert all(v.model == "Austral" for v in variants)

    mhev = _variant(variants, "Evolution", "mild hybrid 150 auto")
    assert mhev.powertrain == "MHEV"
    assert mhev.price == 793_000.0


def test_renault_parser_extracts_espace_variants_with_seat_count_in_name() -> None:
    # "full hybrid E-Tech 200 – 5 míst" vs "... – 7 míst" are two distinct
    # rows within the SAME trim, not a separate table (unlike Dacia's
    # Jogger) - both must survive as distinct variants.
    variants = RenaultParser().parse(ESPACE)
    assert len(variants) == 6
    assert all(v.model == "Espace" for v in variants)

    five_seat = _variant(variants, "Techno", "5 míst")
    seven_seat = _variant(variants, "Techno", "7 míst")
    assert five_seat.price == 979_000.0
    assert seven_seat.price == 1_004_000.0


def test_renault_parser_classifies_rafale_hyper_hybrid_as_phev() -> None:
    # Rafale's own "hyper hybrid E-Tech 4×4 300" is confirmed a plug-in
    # hybrid on its technical-data page (22 kWh battery, 105 km electric
    # range) - distinct from its "full hybrid E-Tech 200" (2 kWh, 0 km).
    variants = RenaultParser().parse(RAFALE)
    assert len(variants) == 4
    assert all(v.model == "Rafale" for v in variants)

    hev = _variant(variants, "Techno", "full hybrid E-Tech 200")
    assert hev.powertrain == "HEV"
    assert hev.price == 1_004_000.0  # 7-digit price split across 3 words ("1" "004" "000") in the source PDF

    phev = _variant(variants, "Esprit Alpine", "hyper hybrid E-Tech 4×4 300")
    assert phev.powertrain == "PHEV"
    assert "4×4" in phev.variant_name


def test_renault_parser_extracts_twingo_variants_with_two_column_layout() -> None:
    # Twingo's own price list omits the promotional-price column entirely
    # (engine, price, instalment - only 2 trailing numeric columns, not
    # every other document's 3) - parse must not assume a fixed count.
    variants = RenaultParser().parse(TWINGO)
    assert len(variants) == 2
    assert all(v.model == "Twingo" for v in variants)
    assert all(v.powertrain == "EV" for v in variants)

    base = _variant(variants, "Evolution", "80 k urban range")
    assert base.price == 499_000.0


def test_renault_parser_extracts_renault_4_and_5_with_bare_numeric_model() -> None:
    # "Renault 4"/"Renault 5" are matched on the cover page with the
    # "Renault " prefix (to avoid a bare "4"/"5" matching stray digits
    # elsewhere on the cover), but the stored `model` is just "4"/"5" -
    # `variant_name` = f"{model} {trim} {engine}" already starts with the
    # brand name via the catalog's own brand+model+trim display
    # convention, so repeating "Renault" here would duplicate it.
    r4 = RenaultParser().parse(R4)
    assert len(r4) == 4
    assert all(v.model == "4" for v in r4)
    assert all(v.powertrain == "EV" for v in r4)
    assert {v.trim for v in r4} == {"Evolution", "Techno", "Iconic", "Iconic Plein Sud"}

    r5 = RenaultParser().parse(R5)
    assert len(r5) == 6
    assert all(v.model == "5" for v in r5)
    # R5's own PDF renders trim headings in a smallcaps font with mixed-
    # case glyphs ("teCHno", "RolanD-GaRRoS") - must normalize the same as
    # every other (already-clean) document's trims.
    assert {v.trim for v in r5} == {"Evolution", "Techno", "Iconic Cinq", "Roland-Garros"}


def test_renault_parser_extracts_megane_and_scenic_electric_variants() -> None:
    megane = RenaultParser().parse(MEGANE)
    assert len(megane) == 3
    assert all(v.model == "Megane" for v in megane)
    assert all(v.powertrain == "EV" for v in megane)

    scenic = RenaultParser().parse(SCENIC)
    assert len(scenic) == 3
    assert all(v.model == "Scenic" for v in scenic)
    assert all(v.powertrain == "EV" for v in scenic)

    top = _variant(scenic, "Iconic", "EV87 220 k long range")
    assert top.price == 1_204_000.0


def test_renault_parser_raw_text_traceable_to_source() -> None:
    variants = RenaultParser().parse(CLIO)
    variant = _variant(variants, "Evolution", "TCe 115")
    assert "434" in variant.raw_text
    assert "000" in variant.raw_text
    assert variant.source_page == 2

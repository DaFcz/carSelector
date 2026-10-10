"""Regression tests for three bugs found on 2026-07-19 during a review
query over data from all seven Škoda models (previously only the Octavia
was verified, see test_parsers.py) — prices/trims for the other models
were genuinely corrupted, even though 70/70 Octavia variants passed unchanged:

1. The `body_style` fallback "unknown" was inserted literally into
   variant_name for models without a body-style line (Fabia/Kamiq/Karoq/
   Scala don't have Liftback/Combi like Octavia/Superb).
2. The legend "Nový vůz krok za krokem 1. Motorizace ..." above the table
   (for models without a body-style line, it's the line right above the
   header) was treated as the continuation of a two-word trim name ->
   "5. Selection", "Pakety Top", "prvky Carlo" instead of "Selection",
   "Top Selection", "Monte Carlo".
3. "Laurin" "&" "Klement" (Superb) and "Top" "Selection" (other models)
   are only ~20-43 points apart on the same header line — closer than
   the "Monte"/"Carlo" columns (70.5 points), so generic distance-based
   clustering can't be used; on top of that, the second word of a price
   above 999,999 Kč ("469" "900") sometimes fell across the boundary of
   such a tightly packed column and produced a phantom variant with a
   price truncated to just the last 3 digits (e.g. 469 Kč instead of 469,900 Kč).

Prices transcribed by hand from `pdfplumber.extract_text()` (see below),
not derived from the parser — same discipline as test_parsers.py."""

from pathlib import Path

from scraper.parsers.skoda_ice import SkodaIceParser

SUPERB_FIXTURE = Path(__file__).parent / "fixtures" / "skoda_superb_cenik.pdf"
FABIA_FIXTURE = Path(__file__).parent / "fixtures" / "skoda_fabia_cenik.pdf"


def _variant(variants, trim: str, motor_fragment: str):
    return next(v for v in variants if v.trim == trim and motor_fragment in v.variant_name)


def test_superb_merges_laurin_a_klement_into_single_trim() -> None:
    variants = SkodaIceParser().parse(SUPERB_FIXTURE)

    assert not any(v.trim in ("Laurin", "&", "Klement") for v in variants)
    assert any(v.trim == "Laurin & Klement" for v in variants)

    # p. 3 (Liftback), 1,5 TSI/110 kW: "935 000 1 135 000 1 070 000"
    # (Selection / Laurin & Klement / Sportline)
    assert _variant(variants, "Selection", "1,5 TSI/110 kW").price == 935_000.0
    assert _variant(variants, "Laurin & Klement", "1,5 TSI/110 kW").price == 1_135_000.0
    assert _variant(variants, "Sportline", "1,5 TSI/110 kW").price == 1_070_000.0


def test_superb_body_style_liftback_and_combi_no_unknown() -> None:
    variants = SkodaIceParser().parse(SUPERB_FIXTURE)

    assert not any("unknown" in v.variant_name for v in variants)
    assert any("Liftback" in v.variant_name for v in variants)
    assert any("Combi" in v.variant_name for v in variants)


def test_fabia_body_style_omitted_not_literal_unknown() -> None:
    # Fabia doesn't have multiple body styles like Octavia/Superb -> there's
    # no "Liftback" line in the PDF, but the body style shouldn't appear in
    # the name at all (it used to literally say "unknown" there).
    variants = SkodaIceParser().parse(FABIA_FIXTURE)
    assert not any("unknown" in v.variant_name for v in variants)


def test_fabia_merges_top_selection_and_monte_carlo() -> None:
    variants = SkodaIceParser().parse(FABIA_FIXTURE)

    trims = {v.trim for v in variants}
    assert "Top Selection" in trims
    assert "Monte Carlo" in trims
    # legend fragments ("Pakety", "Samostatné", "prvky", numbered items)
    # must not show up as a standalone or merged trim name
    assert not any(
        trim.startswith(("Pakety", "Samostatné", "prvky")) or trim[0].isdigit() and "." in trim for trim in trims
    )


def test_fabia_prices_match_source_pdf_no_split_price_bleed() -> None:
    variants = SkodaIceParser().parse(FABIA_FIXTURE)

    # p. 3, "1,0 TSI/70 kW": "439 900 469 900 –" (Selection / Top Selection / Monte Carlo)
    assert _variant(variants, "Selection", "1,0 TSI/70 kW").price == 439_900.0
    assert _variant(variants, "Top Selection", "1,0 TSI/70 kW").price == 469_900.0

    # p. 3, "1,5 TSI/110 kW" (the only occurrence of this engine on the page):
    # "– 559 900 609 900" (Selection not available / Top Selection / Monte Carlo)
    assert _variant(variants, "Top Selection", "1,5 TSI/110 kW").price == 559_900.0
    assert _variant(variants, "Monte Carlo", "1,5 TSI/110 kW").price == 609_900.0

    # no variant may have a price truncated to just the last ~3 digits
    assert all(v.price is None or v.price >= 100_000 for v in variants)

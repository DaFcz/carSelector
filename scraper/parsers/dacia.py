"""Parser for Dacia's per-model "Ceník" price lists (verified against real
PDFs downloaded 2026-09-07 from dacia.cz's asset CDN, effective 1 July/
1 August 2026 depending on model — see scraper/tests/fixtures/dacia_*.pdf).

Like Kia/Toyota/VW (and unlike Škoda's single combined listing), Dacia
publishes one PDF per model — DaciaDiscoverer resolves six URLs (Spring,
Sandero, Sandero Stepway, Jogger, Duster, Bigster), and DaciaParser reads
each independently, extracting the model name itself from the cover page
(same reason VW/Kia do this: the discoverer's own model key never reaches
the parser, see monitors/source_monitor.py) rather than trusting it. The
cover page's own casing is unreliable enough that a substring match against
the known current lineup (`_KNOWN_MODELS`, longest name first so "Sandero
Stepway" doesn't get read as plain "Sandero") is more robust than parsing a
specific line: Duster's cover repeats the name twice ("DUSTER DUSTER"),
Spring's mixes case within one word ("cENÍK"), and Jogger/Bigster's price-
table headers do too ("MOtOR", "SpláTKa*") — evidently a smallcaps-style
font whose actual glyphs are mixed-case, not a text-transform CSS effect
`extract_text()` would already have normalized away.

Every model's price table is on a single page, one row reading e.g.:

    Essential Eco-G 120 Dacia LPG Kalkulačka 441 900 5 133

trim (only present on a row that starts a new trim group - see below),
engine description (contains its own digits - "120", "140" - so it can't
be told apart from the price by "is a digit" alone), an optional "Dacia
LPG Kalkulačka" annotation (a fixed link label pointing at an LPG cost
calculator - it appears on whichever specific engine row happens to link
to it, not consistently the same one across models, so it's stripped by
exact text match rather than by position), then TWO price-like columns:
the list price (kept as `price`) and a monthly-financing estimate (read
then discarded, same "the columns that don't map to a schema field are
read then skipped" convention as every other brand here).

Rows are split into words by `_pdf_layout.group_into_lines`, then into
column clusters by x-gap (`_cluster_by_gap`): the gap between two words of
the same logical column is always ~2.5-3pt (a price/monthly continuation
number, or "mild"/"hybrid" in "mild hybrid 140"), while every real gap
between columns - trim/engine, engine/annotation, annotation/price, price/
monthly - is at least 24.5pt (verified against real word x0/x1 coordinates
across all six fixtures); `_GAP_THRESHOLD` sits well inside that margin.
This makes a row's own shape self-describing: the LAST cluster is always
the monthly figure (discarded), the one before it the price, and - once
the "Dacia LPG Kalkulačka" cluster (if any) is dropped - whatever's left is
EITHER just the engine text (row continues the current trim) OR trim-then-
engine (two clusters - a new trim group starts). No column x-position needs
to be hardcoded or read off the header for this, unlike BMW/Mercedes-Benz -
a deliberate difference from those, since here the columns' own x0 shifts
by model (Sandero's engine column starts at x0=133.2, Duster/Bigster's at
121.9, Jogger's at 147.4 - all verified), apparently because the price-list
template narrows the trim column to fit each model's own longest trim name.

Jogger is the only model whose one page holds TWO price tables ("VÝBAVA
MOTOR 5 Míst SPLÁTKA" / "... 7 Míst ...", back to back - a 5-seat and a
7-seat price list for the same trim/engine combinations, not two columns of
one table) - `parse` re-reads the "N Míst" marker every time it hits a
header line (same "look for the header on every line, not just once"
principle as SkodaEvParser's two body-style tables) and folds it into
`variant_name` (not `model` - it's a seat-count configuration of the same
Jogger, not a different model), which also keeps
scripts/import_scraper_data.py's powertrain_signature() (dedups by
variant_name with trim stripped out) from collapsing the two tables'
otherwise-identical "Essential Eco-G 120" rows onto each other.

Powertrain is classified from the row's own engine text: "electric" -> EV
(Spring only), "mild hybrid" -> MHEV, plain "hybrid" (no "mild") -> HEV,
everything else (Eco-G/TCe, LPG-capable or not) -> ICE. This is a
simplification verified against Duster's own technical-data page (page
10): the "hybrid 150 4×4"/"hybrid-G 150 4×4" rows are classified there as
"mild hybrid" under "Úroveň elektrifikace", not "full hybrid" like plain
"hybrid 155" - i.e. the technical-data page's own classification doesn't
match the price table's naming for those two rows. Reading the price
table's engine text is still what every other brand's parser here does
(Kia/Toyota's HEV/PHEV, Mazda/BMW's EV/PHEV), and cross-referencing a
different page's table by row position would be far more fragile than the
value it adds for two rows on one model - a known, accepted gap rather
than a silently wrong "fix".

Like Kia/Toyota/Hyundai/Mercedes-Benz/Mazda/BMW, the cover/disclaimer text
reads "platné od D. M. RRRR" (lowercase, no "Platnost") - doesn't match
`_pdf_layout.extract_release_date`'s "Platnost od ..." pattern, so
`release_date` stays None here too; VariantRepository falls back to the
download date."""
from __future__ import annotations

from pathlib import Path

import pdfplumber

from ._pdf_layout import group_into_lines, line_text
from .base import BaseParser, ExtractedVariant
from .dacia_equipment import parse_standard_equipment

# Longest name first, so "Sandero Stepway"'s cover page isn't misread as plain "Sandero".
_KNOWN_MODELS = ("Sandero Stepway", "Sandero", "Bigster", "Duster", "Jogger", "Spring")
_ANNOTATION = ("Dacia", "LPG", "Kalkulačka")
_GAP_THRESHOLD = 10.0  # pt; intra-cluster gaps are ~2.5-3pt, the smallest real column gap is 24.5pt


def _extract_model_name(pdf: pdfplumber.PDF) -> str:
    """Args:
        pdf: The opened price-list PDF.

    Returns:
        The canonical model name matched against `_KNOWN_MODELS` (see
        module docstring for why a substring match beats parsing a
        specific cover-page line), or "unknown" if none matched.
    """
    cover_text = (pdf.pages[0].extract_text() or "").upper()
    for model in _KNOWN_MODELS:
        if model.upper() in cover_text:
            return model
    return "unknown"


def _cluster_by_gap(line: list[dict]) -> list[list[dict]]:
    """Args:
        line: One line's words, already sorted left to right (see module
            docstring for the gap sizes this relies on).

    Returns:
        `line` split into column clusters wherever the gap to the
        previous word's `x1` exceeds `_GAP_THRESHOLD`.
    """
    if not line:
        return []
    clusters: list[list[dict]] = [[line[0]]]
    for word in line[1:]:
        if word["x0"] - clusters[-1][-1]["x1"] > _GAP_THRESHOLD:
            clusters.append([word])
        else:
            clusters[-1].append(word)
    return clusters


def _is_digits_cluster(cluster: list[dict]) -> bool:
    return bool(cluster) and all(w["text"].isdigit() for w in cluster)


def _cluster_text(cluster: list[dict]) -> str:
    return " ".join(w["text"] for w in cluster)


def _classify_powertrain(engine: str) -> str:
    lowered = engine.lower()
    if "electric" in lowered:
        return "EV"
    if "mild hybrid" in lowered:
        return "MHEV"
    if "hybrid" in lowered:
        return "HEV"
    return "ICE"


def _seats_label(line: list[dict]) -> str | None:
    """Args:
        line: A price-table header line ("VÝBAVA MOTOR [N Míst] SPLÁTKA...").

    Returns:
        `"N míst"` if this header carries a seat-count sub-table label
        (Jogger only - see module docstring), else `None`.
    """
    texts = [w["text"] for w in line]
    for i, text in enumerate(texts):
        if text.isdigit() and i + 1 < len(texts) and texts[i + 1].lower() == "míst":
            return f"{text} míst"
    return None


def _is_header_line(line: list[dict]) -> bool:
    texts_upper = {w["text"].upper() for w in line}
    return "VÝBAVA" in texts_upper and "MOTOR" in texts_upper


def _parse_row(
    line: list[dict],
    model: str,
    seats: str | None,
    trim: str | None,
    source_page: int,
    equipment_by_trim: dict[str, dict[str, str]],
) -> tuple[ExtractedVariant | None, str | None]:
    """Args:
        line: One line's words from the price table (a data row, or
            leftover marketing/legal text below the table - header lines
            are filtered out by the caller before this is reached).
        model: This document's model name (from `_extract_model_name`).
        seats: The current "N míst" sub-table label (Jogger only), or
            `None` for every other model.
        trim: The trim in effect so far (from the last row that started
            a new trim group) - carried forward when a row has no trim
            column of its own.
        source_page: 1-based page number `line` was read from.
        equipment_by_trim: `{trim: {item_name: "STANDARD"}}` from
            `dacia_equipment.parse_standard_equipment` - looked up by this
            row's own trim, same as `skoda_ice.py`'s
            `equipment_by_trim.get(trim_label, {})`.

    Returns:
        `(variant, trim)` - `variant` is `None` if `line` isn't a price
        row (fewer than two trailing all-digit clusters - true of the
        marketing/legal text below the table, which never ends in two
        bare numbers) or has no trim to attribute the row to yet;
        `trim` is the trim to carry into the next row (unchanged unless
        this row started a new trim group).
    """
    clusters = _cluster_by_gap(line)
    if len(clusters) < 2 or not _is_digits_cluster(clusters[-1]) or not _is_digits_cluster(clusters[-2]):
        return None, trim

    price = float("".join(w["text"] for w in clusters[-2]))

    left = [c for c in clusters[:-2] if tuple(w["text"] for w in c) != _ANNOTATION]
    if len(left) == 2:
        # Spring's cover/table font renders trim names in inconsistent case
        # ("EssEntial", "EXPREssiOn", "EXtREME" - see module docstring's
        # note on the smallcaps-style font) - .capitalize() is a no-op for
        # every other model's already-correct "Essential"/"Expression"/
        # "Journey"/"Extreme".
        trim = _cluster_text(left[0]).capitalize()
        engine = _cluster_text(left[1])
    elif len(left) == 1:
        engine = _cluster_text(left[0])
    else:
        return None, trim
    if trim is None:
        return None, trim

    variant_name = f"{model} {trim} {engine}" + (f" {seats}" if seats else "")

    return (
        ExtractedVariant(
            model=model,
            trim=trim,
            variant_name=variant_name,
            price=price,
            currency="CZK",
            source_page=source_page,
            raw_text=line_text(line),
            powertrain=_classify_powertrain(engine),
            equipment=equipment_by_trim.get(trim, {}),
        ),
        trim,
    )


class DaciaParser(BaseParser):
    brand = "dacia"
    powertrain = "ICE"  # nominal default; the actual powertrain is per-row, see _classify_powertrain

    def parse(self, pdf_path: Path) -> list[ExtractedVariant]:
        """See module docstring for the row/cluster shape and the Jogger
        5/7-seat double table.

        Args:
            pdf_path: Local path to a downloaded Dacia price-list PDF.

        Returns:
            One `ExtractedVariant` per price row found on the page(s)
            with a "VÝBAVA MOTOR ... SPLÁTKA" header, with `equipment`
            populated from the "Hlavní prvky sériové výbavy" overview page
            (see `dacia_equipment.parse_standard_equipment`).
        """
        variants: list[ExtractedVariant] = []

        with pdfplumber.open(pdf_path) as pdf:
            model = _extract_model_name(pdf)
            equipment_by_trim = parse_standard_equipment(pdf)

            for page in pdf.pages:
                lines = group_into_lines(page.extract_words())
                if not any(_is_header_line(line) for line in lines):
                    continue  # page without a price table (specs, equipment, accessories, ...)

                seats: str | None = None
                trim: str | None = None
                for line in lines:
                    if _is_header_line(line):
                        seats = _seats_label(line)
                        trim = None
                        continue
                    variant, trim = _parse_row(line, model, seats, trim, page.page_number, equipment_by_trim)
                    if variant is not None:
                        variants.append(variant)

        return variants

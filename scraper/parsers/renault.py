"""Parser for Renault's per-model "Ceník" price lists (verified against
real PDFs downloaded 2026-09-12 from Renault Group's asset CDN, effective
1 August-10 September 2026 depending on model — see scraper/tests/fixtures/
renault_*.pdf). Covers the full current CZ personal-car lineup with a
price list of its own: Clio, Captur, Symbioz, Arkana, Austral, Espace,
Rafale, Twingo, Renault 4, Renault 5, Megane and Scenic (the last five are
"e-tech elektrický" - electric-only - documents; Kangoo/Trafic/Master are
commercial vehicles, out of scope for a personal car selector).

Renault shares its parent Renault Group's own CDN with Dacia
(`cdn.group.renault.com/ren/...` vs. Dacia's `.../dac/...`), but the price-
list PDF template itself is different - closer to Kia's shape (a trim
heading, then one row per engine underneath) than Dacia's. A row reads,
e.g.:

    TCe 115 434 000 399 000 4 050

engine, then TWO OR THREE trailing numeric columns depending on the
model/document - always "ceníková cena" (the list price, kept as `price`,
matching every other brand's convention) first, then 0-1 promotional/
bonus-adjusted prices, then a monthly financing instalment last - all read
then discarded except the first. Twingo's own price list omits the
promotional column entirely (engine, price, instalment - just two trailing
numbers); every other document here has three. Rather than assume a fixed
column count, `_parse_row` counts how many ALL-DIGIT clusters trail the
line and takes the first (leftmost) one as `price`, whatever that count
turns out to be - see that function's own docstring.

Column detection reuses the same word-gap clustering Dacia's and Ford's
parsers use (`_cluster_by_gap`): the gap between two words of the same
logical column (a thousands-separator continuation like "434"/"000", or
adjoining words within the engine text like "full"/"hybrid"/"E-Tech"/"160")
is consistently ~1.7-1.8pt, while the real gap between the engine text and
the first price column is 150pt+ (verified against real word coordinates
across all twelve fixtures) - `_GAP_THRESHOLD` sits well inside that
margin, so an engine description ending in its own digit (e.g. "TCe 115",
"full hybrid E-Tech 160") is never mistaken for the start of the price
columns: the digit stays clustered with its own non-digit neighbours,
and a cluster with even one non-digit word in it never counts as a price
column.

Trim headings ("EVOLUTION", "TECHNO", "ESPRIT ALPINE", ...) are printed in
consistent ALL CAPS in most of these documents, but the electric Renault
5's PDF renders them in a smallcaps-style font with genuinely mixed-case
glyphs ("teCHno", "RolanD-GaRRoS" - same underlying quirk as Dacia's own
smallcaps font, see dacia.py's module docstring) - `.title()` normalizes
both to the same "Techno"/"Roland-Garros" spelling `parse` uses everywhere
else, and is a no-op for the already-correct documents.

Powertrain is classified from the row's own engine text - Renault's own
"Úroveň elektrifikace" (electrification level) terminology, verified
against Rafale's technical-data page: "mild hybrid" -> MHEV, "full hybrid"
-> HEV, "hyper hybrid" -> PHEV (Rafale's own plug-in variant, confirmed by
its spec page listing a 22 kWh traction battery and 105 km electric-only
range under that exact name, vs. "full hybrid"'s 2 kWh/0 km) - except for
the five documents that are themselves entirely electric (Twingo/4/5/
Megane/Scenic's own "e-tech elektrický" price lists), which don't repeat
an electric marker on every row the way Cupra's kWh/100km consumption
figure does - `_ELECTRIC_MODELS` classifies every row in those five as EV
directly from the model, not the row text.

Like most other brands here, the cover page carries no usable release
date (just the model name over a version subtitle) - the real "Platnost
ceníku od D. M. RRRR" disclaimer is on the price-table page instead, same
gap as CUPRA's own (see cupra.py's module docstring) - so `release_date`
stays None; VariantRepository falls back to the download date.

`equipment` is populated per-trim from each document's own "hlavní prvky
sériové výbavy" overview page, for the seven of the twelve models whose own
PDF lays that page out as a single column - see
`renault_equipment.parse_standard_equipment`'s own module docstring for
which those are and why the other five (a two-side-by-side-columns layout)
are a known, accepted gap instead."""
from __future__ import annotations

from pathlib import Path

import pdfplumber

from ._pdf_layout import group_into_lines, line_text
from .base import BaseParser, ExtractedVariant
from .renault_equipment import parse_standard_equipment

# Cover-page text (uppercased) -> canonical model name. "RENAULT 4"/
# "RENAULT 5" need the "RENAULT " prefix to disambiguate from a bare "4"/
# "5" appearing elsewhere on the cover (e.g. within a date) - every other
# model's own name is already unambiguous on its own.
_KNOWN_MODELS = {
    "RENAULT 4": "4",
    "RENAULT 5": "5",
    "ESPACE": "Espace",
    "RAFALE": "Rafale",
    "CAPTUR": "Captur",
    "SYMBIOZ": "Symbioz",
    "ARKANA": "Arkana",
    "AUSTRAL": "Austral",
    "CLIO": "Clio",
    "TWINGO": "Twingo",
    "MEGANE": "Megane",
    "SCENIC": "Scenic",
}
# These five documents are themselves entirely electric (an "e-tech
# elektrický" price list) - see module docstring for why powertrain is
# classified from the model here, not the row text, for just these five.
_ELECTRIC_MODELS = {"Twingo", "4", "5", "Megane", "Scenic"}
_END_OF_TABLE_MARKER = "Ceníková cena a případné obchodní akce jsou platné do"
_GAP_THRESHOLD = 10.0  # pt; intra-cluster gaps are ~1.7-1.8pt, the smallest real column gap is 150pt+


def _extract_model_name(pdf: pdfplumber.PDF) -> str:
    """Args:
        pdf: The opened price-list PDF.

    Returns:
        The canonical model name matched against `_KNOWN_MODELS` (a
        substring match against the whole cover page, not a specific
        line - the cover's own line-wrapping varies: some read "RENAULT"/
        "<MODEL>" on two lines, others "RENAULT <MODEL>" on one, and the
        electric documents add an "e-tech"/"elektrický" subtitle either
        before or after the model name), or "unknown" if none matched.
    """
    cover_text = (pdf.pages[0].extract_text() or "").upper()
    for pattern, model in _KNOWN_MODELS.items():
        if pattern in cover_text:
            return model
    return "unknown"


def _is_header_line(line: list[dict]) -> bool:
    texts = {w["text"].lower() for w in line}
    return "verze" in texts and "ceníková" in texts


def _cluster_by_gap(words: list[dict]) -> list[list[dict]]:
    """Args:
        words: One line's words, already sorted left to right.

    Returns:
        `words` split into clusters wherever the gap to the previous
        word's `x1` exceeds `_GAP_THRESHOLD` - see module docstring for
        the gap sizes this relies on.
    """
    if not words:
        return []
    clusters: list[list[dict]] = [[words[0]]]
    for word in words[1:]:
        if word["x0"] - clusters[-1][-1]["x1"] > _GAP_THRESHOLD:
            clusters.append([word])
        else:
            clusters[-1].append(word)
    return clusters


def _is_all_digits(cluster: list[dict]) -> bool:
    return bool(cluster) and all(w["text"].isdigit() for w in cluster)


def _classify_powertrain(model: str, engine: str) -> str:
    if model in _ELECTRIC_MODELS:
        return "EV"
    lowered = engine.lower()
    if "hyper hybrid" in lowered:
        return "PHEV"
    if "mild hybrid" in lowered:
        return "MHEV"
    if "full hybrid" in lowered:
        return "HEV"
    return "ICE"


def _parse_row(
    line: list[dict],
    model: str,
    trim: str | None,
    source_page: int,
    equipment_by_trim: dict[str, dict[str, str]],
) -> ExtractedVariant | None:
    """Args:
        line: One line's words from the price table (a data row, a trim
            heading, or leftover legal/promo text below the table).
        model: This document's model name (from `_extract_model_name`).
        trim: The trim currently in effect (from the last heading line
            seen) - `None` if no heading has been seen yet on this page.
        source_page: 1-based page number `line` was read from.
        equipment_by_trim: `{trim: {item_name: "STANDARD"}}` from
            `renault_equipment.parse_standard_equipment` - looked up by
            this row's own trim, same as `dacia.py`'s `_parse_row`.

    Returns:
        The row's `ExtractedVariant`, or `None` if `line` isn't a price
        row - fewer than two trailing all-digit clusters (a trim heading,
        which has none, or a row missing its own price data entirely,
        which `parse` distinguishes by the same "does it have ANY
        trailing digit cluster" check - see that method) - or no trim
        heading has been seen yet.
    """
    if trim is None:
        return None

    clusters = _cluster_by_gap(line)
    trailing_digit_count = 0
    for cluster in reversed(clusters):
        if _is_all_digits(cluster):
            trailing_digit_count += 1
        else:
            break
    if trailing_digit_count < 2:
        return None

    price_cluster = clusters[-trailing_digit_count]
    price = float("".join(w["text"] for w in price_cluster))
    engine = line_text([w for c in clusters[: -trailing_digit_count] for w in c]).strip()
    if not engine:
        return None

    return ExtractedVariant(
        model=model,
        trim=trim,
        variant_name=f"{model} {trim} {engine}".strip(),
        price=price,
        currency="CZK",
        source_page=source_page,
        raw_text=line_text(line),
        powertrain=_classify_powertrain(model, engine),
        equipment=equipment_by_trim.get(trim, {}),
    )


class RenaultParser(BaseParser):
    brand = "renault"
    powertrain = "ICE"  # nominal default; the actual powertrain is per-row/per-model, see _classify_powertrain

    def parse(self, pdf_path: Path) -> list[ExtractedVariant]:
        """See module docstring for the row shape and known gaps.

        Args:
            pdf_path: Local path to a downloaded Renault price-list PDF.

        Returns:
            One `ExtractedVariant` per price row found on the page(s)
            with a "verze ... ceníková cena ..." header, with `equipment`
            populated from the "hlavní prvky sériové výbavy" overview page
            where that page's own layout allows it (see
            `renault_equipment.parse_standard_equipment`).
        """
        variants: list[ExtractedVariant] = []

        with pdfplumber.open(pdf_path) as pdf:
            model = _extract_model_name(pdf)
            equipment_by_trim = parse_standard_equipment(pdf)

            for page in pdf.pages:
                lines = group_into_lines(page.extract_words())
                if not any(_is_header_line(line) for line in lines):
                    continue  # page without a price table (specs, equipment, accessories, ...)

                trim: str | None = None
                for line in lines:
                    text = line_text(line)
                    if _is_header_line(line):
                        continue
                    if text.startswith(_END_OF_TABLE_MARKER):
                        break

                    variant = _parse_row(line, model, trim, page.page_number, equipment_by_trim)
                    if variant is not None:
                        variants.append(variant)
                    elif not any(w["text"].isdigit() for w in line):
                        # A genuine trim heading ("EVOLUTION", "ESPRIT
                        # ALPINE", ...) never contains a digit. A line
                        # that DOES but still didn't produce a variant is
                        # an incomplete/malformed row - skipped without
                        # touching `trim`, not mistaken for a new heading.
                        trim = text.title().strip()

        return variants

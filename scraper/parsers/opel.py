"""Parser for Opel's per-model "Ceníkové a akční ceny" price lists
(verified against real PDFs downloaded 2026-09-12/13 from opel.cz,
effective 7-30 September 2026 - see scraper/tests/fixtures/opel_*.pdf).
Covers the current CZ personal-car lineup with a price list of its own:
Corsa, Astra (hatchback "HB" and "Sports Tourer" wagon, each combining ICE
and Plug-in Hybrid trims in one document), the shared Astra electric
document (covering both body styles), Mokka, Frontera and Grandland
(itself combining ICE and Plug-in Hybrid) - each also with its own
all-electric document. Combo/Vivaro/Movano commercial vehicles are out of
scope, same convention as every other brand here.

Opel's own price table is a genuine grid, but a much simpler one than
Ford's: one column per field (trim/LCDV code/engine/fuel/transmission/list
price/discount/promotional price for combustion & hybrid documents; trim/
LCDV/engine/battery/range/list price/discount/promotional price for the
all-electric ones), one row per engine - closer to Kia's "list" shape than
Ford's matrix, just laid out as real table columns rather than a single
text line per row. This needed a genuine column-position parser rather
than a text-line regex (like Kia's or Renault's), for two reasons
specific to this layout - plus a third that ruled out reusing `_pdf_layout
.column_for_x` (Škoda's own column-position helper) as-is:

1. The trim column is a single cell VERTICALLY MERGED across every engine
   row it covers, vertically centered against that whole group rather
   than repeated per row (verified against a rendered page image - a
   naive `extract_text()` reads a merged trim label as if it were its own
   text line, in reading position order relative to the *nearest* row,
   not the whole group it spans). `_nearest_trim` assigns each row to
   whichever trim heading's own y-position is closest - correct
   regardless of whether a group has 2 rows (heading centered in the gap
   between them) or 3 (heading landing almost exactly on the middle row's
   own baseline) or 1 (the all-electric documents' own simpler layout,
   where the trim is printed inline on the row's own line rather than
   merged - "nearest" is trivially that same row, distance 0).
2. The engine (and, on combustion/hybrid documents, transmission) column
   text wraps onto its own line just above and/or below the row's actual
   data baseline (verified the same way) - e.g. "Hybrid 1.2 TURBO
   (107kW/145k)" above, "Start/Stop eDCT6" below, both belonging to ONE
   row whose LCDV code/prices sit on the baseline between them. Each row
   is anchored by its own LCDV product code (`_LCDV_RE` - a fixed-length,
   fixed-shape token nothing else on the page matches), and every word
   within `_ROW_WINDOW` points of that code's own y-position is pulled
   into the row regardless of which of these 1-3 physical lines it's
   printed on.
3. Column contents aren't reliably left-aligned to their own header, in
   either direction - a wide MOTOR value like "(81kW/110k)" can start
   past the midpoint toward PALIVO's own anchor (there's no shortage of
   horizontal room in this column, so its wrapped sub-lines don't hug the
   left edge the way a narrower field would), while a wide SLEVA value
   like "100.000" starts further left than a narrower one in the same
   column (numbers right-align within their own cell). `column_for_x`'s
   own left-edge-plus-small-tolerance scheme assumes neither happens;
   `_column_for_x` here uses MIDPOINT boundaries between adjacent header
   anchors instead (immune to the second case), and PALIVO/PŘEVODOVKA are
   dropped from the boundary set entirely rather than tuned around (immune
   to the first) - see that function's and the boundary-building code's
   own comments for both.

Column positions themselves aren't hardcoded (verified they shift by
~50pt between Corsa's and Grandland's own documents) - `_column_anchors`
reads them straight off each page's own header row every time, the same
principle as every position-based parser here. One document (Mokka
Electric) mislabels its LCDV-code column header as "MOTOR" too instead of
"LCDV KÓD" - `_column_anchors` special-cases a repeated "MOTOR" label,
see its own comment.

Prices use "." as the thousands separator ("459.990", or "1.049.990" for
a 7-digit one) - `_parse_price` just strips every "." (no field here ever
needs a fractional-Kč value, so this is unambiguous). `price` is read from
"CENÍKOVÁ CENA" (the list price), filtered through `_PRICE_TOKEN_RE` to
drop any non-numeric word that ends up in that bucket (harmless spillover
from the boundary approach above, e.g. the all-electric documents' own
"DOJEZD" unit "km") - "SLEVA" (discount) and "AKČNÍ CENA" (the resulting
promotional price) are read then discarded, same convention as every
other brand's own promotional column here.

Powertrain is classified from the engine column's own text: "PHEV" is
printed literally for Opel's plug-in hybrids (e.g. "1.6 TURBO (143 kW/
195k) PHEV"); "Elektromotor" for the all-electric documents; "Hybrid"
otherwise is Opel/Stellantis's own 48V mild-hybrid tech (confirmed against
Corsa's technical-data page, which lists "Trakce: mild-hybrid" for the row
whose price-table engine text just says "Hybrid") - matches MHEV, not
HEV; everything else is plain ICE.

Like most other brands here, the cover page carries no usable date - the
real "Ceník platí od D. M. do D. M. RRRR" validity line is a closed
campaign window on the price-table page itself (not the single, open-
ended "Platnost od" date `_pdf_layout.extract_release_date` looks for, on
top of being on the wrong page anyway - see CUPRA's and Renault's own
module docstrings for that half of the same gap), so `release_date` stays
None; VariantRepository falls back to the download date."""
from __future__ import annotations

import re
from pathlib import Path

import pdfplumber

from ._pdf_layout import group_into_lines, line_text
from .base import BaseParser, ExtractedVariant
from .opel_equipment import parse_standard_equipment, resolve_trim_equipment

_KNOWN_MODELS = (
    "Astra Sports Tourer",
    "Astra",
    "Corsa",
    "Mokka",
    "Frontera",
    "Grandland",
)
_LCDV_RE = re.compile(r"^[A-Z0-9]{16}$")
_HEADER_TOP_WINDOW = 10.0  # pt; the header's own 2-3 physical sub-lines are ~5.4pt apart
_ROW_WINDOW = 7.0  # pt; a row's own wrapped engine/transmission lines sit ~4-5.5pt above/below its baseline
_COLUMN_LABELS = ("VÝBAVA", "LCDV", "MOTOR", "PALIVO", "PŘEVODOVKA", "BATERIE", "DOJEZD", "CENÍKOVÁ", "SLEVA", "AKČNÍ")


def _extract_model_name(pdf: pdfplumber.PDF) -> str:
    """Args:
        pdf: The opened price-list PDF.

    Returns:
        The canonical model name matched against `_KNOWN_MODELS` (a
        substring match, longest name first so "Astra Sports Tourer" isn't
        misread as plain "Astra"), or "unknown" if none matched.

        Unlike every other brand parsed here, the model name isn't printed
        anywhere on Opel's own price-table page (verified against a
        rendered image - the page opens directly with "CENÍKOVÉ A AKČNÍ
        CENY", no title above it) or the immediately following equipment
        pages; it only shows up several pages in, on the financing-example
        and technical-data pages (e.g. "TECHNICKÁ ÚDAJE - CORSA") - so this
        searches every page rather than just the first.
    """
    whole_text = " ".join(re.sub(r"\s+", " ", page.extract_text() or "") for page in pdf.pages).upper()
    for model in _KNOWN_MODELS:
        if model.upper() in whole_text:
            return model
    return "unknown"


def _is_header_line(line: list[dict]) -> bool:
    texts = {w["text"] for w in line}
    return "MOTOR" in texts and ("PŘEVODOVKA" in texts or "BATERIE" in texts)


def _column_anchors(lines: list[list[dict]], header_index: int) -> dict[str, float]:
    """Args:
        lines: The whole page's lines (see `_pdf_layout.group_into_lines`).
        header_index: Index into `lines` of the line `_is_header_line` matched.

    Returns:
        `{column_label: left_x}` for every recognized header label found
        within `_HEADER_TOP_WINDOW` of the header line's own `top` - see
        module docstring for why the header spans more than one physical
        line (a 2-word column heading like "CENÍKOVÁ CENA" prints its two
        words on different sub-lines) and why this window is still narrow
        enough to exclude the page's own title just above it.

        The Mokka Electric document mislabels its LCDV-code column header
        as "MOTOR" too (verified against a rendered image - the header
        literally reads "MOTOR MOTOR" where every other document reads
        "LCDV KÓD MOTOR"), so a repeated "MOTOR" label is a signal on its
        own: when seen and "LCDV" wasn't otherwise found, the leftmost of
        the two is renamed to "LCDV" (matching every other document's own
        column order - LCDV code left of the engine description).
    """
    header_top = lines[header_index][0]["top"]
    header_words = [
        word for line in lines if abs(line[0]["top"] - header_top) <= _HEADER_TOP_WINDOW for word in line
    ]
    anchors: dict[str, float] = {}
    motor_xs: list[float] = []
    for word in header_words:
        text = word["text"].upper()
        if text == "MOTOR":
            motor_xs.append(word["x0"])
        if text in _COLUMN_LABELS and text not in anchors:
            anchors[text] = word["x0"]
    if "LCDV" not in anchors and len(motor_xs) >= 2:
        anchors["LCDV"] = min(motor_xs)
        anchors["MOTOR"] = max(motor_xs)
    return anchors


def _nearest_trim(trim_headings: list[tuple[float, str]], row_top: float) -> str | None:
    """Args:
        trim_headings: `(top, text)` pairs for every trim heading found on
            this page, in any order.
        row_top: The y-position (`top`) of the data row to assign a trim to.

    Returns:
        The heading whose own `top` is closest to `row_top` - see module
        docstring for why a vertically-merged, group-centered heading
        (or, on the all-electric documents, an inline one at distance 0)
        both resolve correctly this way - or `None` if `trim_headings` is empty.
    """
    if not trim_headings:
        return None
    return min(trim_headings, key=lambda pair: abs(pair[0] - row_top))[1]


def _column_for_x(x0: float, names: list[str], anchors: list[float]) -> str:
    """Args:
        x0: A word's own left edge.
        names: Column labels, sorted left-to-right (matches `anchors`).
        anchors: Each column's header left edge, same order as `names`.

    Returns:
        The column `x0` belongs to, decided by MIDPOINT boundaries between
        adjacent header anchors rather than left-edge-plus-tolerance (what
        `_pdf_layout.column_for_x` does) - needed because a wider value in
        a right-aligned numeric column (e.g. "100.000" vs "50.000" in
        SLEVA) starts further left than a narrower one in the same column,
        by more than that helper's small fixed tolerance can absorb
        (verified: a SLEVA "100.000" landed 0.2pt short of column_for_x's
        own tolerance-adjusted boundary and was misclassified into
        CENÍKOVÁ instead, corrupting that row's price). A midpoint boundary
        has no such edge case: it only asks which of two neighboring
        anchors `x0` is closer to.
    """
    idx = 0
    for i in range(len(anchors) - 1):
        if x0 >= (anchors[i] + anchors[i + 1]) / 2:
            idx = i + 1
        else:
            break
    return names[idx]


def _classify_powertrain(engine: str) -> str:
    lowered = engine.lower()
    if "elektromotor" in lowered:
        return "EV"
    if "phev" in lowered:
        return "PHEV"
    if "hybrid" in lowered:
        return "MHEV"
    return "ICE"


_PRICE_TOKEN_RE = re.compile(r"^[\d.]+$")


def _parse_price(text: str) -> float:
    return float(text.replace(".", ""))


class OpelParser(BaseParser):
    brand = "opel"
    powertrain = "ICE"  # nominal default; the actual powertrain is per-row, see _classify_powertrain

    def parse(self, pdf_path: Path) -> list[ExtractedVariant]:
        """See module docstring for the column-grid shape and how a row's
        wrapped engine/transmission text and its vertically-merged trim
        heading are both reconstructed from word positions.

        Args:
            pdf_path: Local path to a downloaded Opel price-list PDF.

        Returns:
            One `ExtractedVariant` per price row found on the page(s)
            with a "MOTOR ... PŘEVODOVKA ..." (or, on the all-electric
            documents, "MOTOR ... BATERIE ... DOJEZD ...") header, with
            `equipment` populated from the "STANDARDNÍ VÝBAVA" page where
            available (see `opel_equipment.parse_standard_equipment`).
        """
        variants: list[ExtractedVariant] = []

        with pdfplumber.open(pdf_path) as pdf:
            model = _extract_model_name(pdf)
            equipment_by_trim = parse_standard_equipment(pdf)

            for page in pdf.pages:
                words = page.extract_words()
                lines = group_into_lines(words)
                header_index = next((i for i, line in enumerate(lines) if _is_header_line(line)), None)
                if header_index is None:
                    continue  # page without a price table (equipment, technical data, ...)

                anchors = _column_anchors(lines, header_index)
                if "VÝBAVA" not in anchors or "LCDV" not in anchors or "CENÍKOVÁ" not in anchors:
                    continue
                # PALIVO/PŘEVODOVKA are dropped from the boundary set
                # entirely (their own values are never read - only MOTOR
                # and CENÍKOVÁ are) rather than kept as boundaries: their
                # column is comparatively narrow, so a wide MOTOR sub-line
                # like "(81kW/110k)" can sit physically closer to PALIVO's
                # own anchor than to MOTOR's, tripping a midpoint boundary
                # there and truncating the engine text. Widening MOTOR
                # across that gap avoids it; anything genuinely PALIVO/
                # PŘEVODOVKA-shaped that lands in the widened MOTOR bucket
                # just becomes harmless extra text there.
                # BATERIE/DOJEZD stay as real boundaries, unlike PALIVO/
                # PŘEVODOVKA above: their own values are pure digits (a
                # kWh figure, a km figure), so dropping them would let that
                # digit-only noise slip straight past the price-token
                # filter below if it ever bled into the CENÍKOVÁ bucket the
                # same way PALIVO/PŘEVODOVKA's text does - unlike text
                # noise, a stray number there wouldn't be filterable.
                names = [name for name in anchors if name not in ("PALIVO", "PŘEVODOVKA")]
                names.sort(key=lambda name: anchors[name])
                xs = [anchors[name] for name in names]

                header_top = lines[header_index][0]["top"]
                trim_boundary = (anchors["VÝBAVA"] + anchors["LCDV"]) / 2
                trim_words = [
                    word
                    for word in words
                    if word["top"] > header_top + _HEADER_TOP_WINDOW and word["x0"] < trim_boundary
                ]
                trim_headings = [
                    (group[0]["top"], line_text(group)) for group in group_into_lines(trim_words)
                ]

                row_anchors = sorted(
                    (word for word in words if word["x0"] >= trim_boundary and _LCDV_RE.match(word["text"])),
                    key=lambda word: word["top"],
                )
                for anchor in row_anchors:
                    row_top = anchor["top"]
                    row_words = [word for word in words if abs(word["top"] - row_top) <= _ROW_WINDOW]

                    by_column: dict[str, list[dict]] = {}
                    for word in row_words:
                        name = _column_for_x(word["x0"], names, xs)
                        by_column.setdefault(name, []).append(word)
                    for column_words in by_column.values():
                        column_words.sort(key=lambda word: (word["top"], word["x0"]))

                    motor = line_text(by_column.get("MOTOR", [])).strip()
                    price_words = [
                        word for word in by_column.get("CENÍKOVÁ", []) if _PRICE_TOKEN_RE.match(word["text"])
                    ]
                    if not motor or not price_words:
                        continue
                    price = _parse_price(line_text(price_words))

                    trim = _nearest_trim(trim_headings, row_top)
                    if trim is None:
                        continue

                    row_words_sorted = sorted(row_words, key=lambda word: (word["top"], word["x0"]))
                    variants.append(
                        ExtractedVariant(
                            model=model,
                            trim=trim,
                            variant_name=f"{model} {trim} {motor}".strip(),
                            price=price,
                            currency="CZK",
                            source_page=page.page_number,
                            raw_text=line_text(row_words_sorted),
                            powertrain=_classify_powertrain(motor),
                            equipment=resolve_trim_equipment(equipment_by_trim, trim),
                        )
                    )

        return variants

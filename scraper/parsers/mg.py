"""Parser for MG's per-model "Ceník" price lists (verified against real
PDFs downloaded 2026-09-13 from mgmotor-czech.cz, effective June-September
2026 depending on model - see scraper/tests/fixtures/mg_*.pdf). Covers
MG3, MGS9 PHEV, MG ZS, MG HS, MG4 EV (Urban), MGS5 EV and MG Cyberster -
MG's entire current CZ lineup as of this verification (unlike most other
brands here, there's no separate commercial-vehicle lineup to exclude -
MG only sells passenger cars in this market).

MG's price table reads like Kia's/Renault's own (a trim heading, then one
row per engine underneath), not a genuine column grid - a line-sequence
reader fits closer than OpelParser's column-position one, but with one
wrinkle neither Kia's nor Renault's own needed: a trim heading covering
more than one engine row is a single cell VERTICALLY MERGED across the
whole group and centered against it (see OpelParser's own docstring point
1 for the same pattern there) - a naive "current trim, carry forward
until the next heading" reader would misplace the last row or two of a
merged group onto the FOLLOWING trim, since the heading's own line can
sit BETWEEN two of the rows it covers, not before all of them (verified
against a rendered page image - MG HS's own document has an entirely
unlabeled first trim group for exactly this reason: its own heading,
"Emotion", is centered against all 4 of its rows and happens to land
between the 2nd and 3rd). `_nearest_trim` - same idea, same name, as
OpelParser's own - assigns each row to whichever trim heading is
vertically closest, correct whether a group has 1 row (heading sits on
that row's own line, distance 0) or several.

Unlike Opel, there's no per-row product code to anchor a row on - MG's
own rows have none - so a line is recognized as a data row simply by
containing a Kč-suffixed price (`_PRICE_RE`, the same regex
PeugeotParser uses). `price` is the FIRST such run on the line (CENA, the
list price) - ZVÝHODNĚNÍ (discount), VÝKUPNÍ BONUS/BONUS PŘI FINANCOVÁNÍ
(a trade-in or financing-only extra discount, on some documents) and
AKČNÍ CENA (the resulting promotional price) are read then discarded the
same as every other brand's own promotional column(s) here - the trailing
column count varies per document (1 to 4 Kč groups) but that never
matters since only the first is read.

Some documents carry a SECOND, promotional-only price table alongside the
regular one: a "skladové vozy" (stock-vehicles-only) one (MG3's own, an
extra discount stacked on the regular one) or a seasonal insert with no
"CENÍK MG <model>" title at all (MG HS's own "SUMMER EDITION" page, a
single row). Both are skipped: a table is only read when the text
immediately above its own header reads "CENÍK MG ..." (in the source PDF
this heading is printed one letter per word - `_looks_like_price_list_title`
strips whitespace before checking) with no "SKLADOV..." word anywhere in
that same text.

`model` is read from the cover page's own "<MODEL> OD <price> Kč" line
(not the giant stylized "CENÍK" heading right above it, which the source
PDF - unlike the model/price line - prints one letter per word), with the
leading "MG" stripped (paralleling Renault's own bare "4"/"5" - `brand`
already supplies "MG" for display) and each remaining word title-cased
except for `_KEEP_UPPERCASE` abbreviations (ZS, HS, EV, PHEV - MG's own
body-style/powertrain suffixes, which would otherwise come out as
"Zs"/"Hs"/"Ev"/"Phev").

Powertrain is classified from the engine text: "PHEV" is printed
literally for MG's plug-in hybrids; "Hybrid+" otherwise is a genuine full
hybrid confirmed via HS's own technical-data page ("BENZÍN, HEV A PHEV")
- HEV, not MHEV; "Synchronní elektromotor" is EV; everything else
(petrol, labelled "Zážehový") is plain ICE. MG doesn't sell diesel in CZ,
so `scripts/import_scraper_data.py`'s diesel regex needed no brand-
specific fix here.

POHON (drivetrain) is printed explicitly per row - "Přední"/"Zadní"/
"4×4" - unlike most other brands here, which don't label it at all (see
`infer_drivetrain`'s own "FWD-default" gap in its docstring). MGS5 EV and
Cyberster both have genuinely rear-wheel-drive trims, so this is kept in
`variant_name`, and `scripts/import_scraper_data.py`'s own
`infer_drivetrain` gained a "zadní" check for it.

Like every other brand here except Škoda/VW, the cover page's own release
date used to fall outside `_pdf_layout.extract_release_date`'s exact
"Platnost od ..." wording ("Platnost ceníku od ...", one extra word) -
that helper's own regex was widened to accept both, so `release_date` is
populated normally here rather than falling back to the download date the
way it does for CUPRA/Renault/Opel/Peugeot.

`equipment` is populated per row from MG's own "VÝBAVA" checkbox-matrix
pages (see `mg_equipment.py`'s own module docstring) - looked up by
`trim`, the same as `dacia.py`'s own `equipment_by_trim.get(trim, {})`."""
from __future__ import annotations

import re
from pathlib import Path

import pdfplumber

from ._pdf_layout import group_into_lines, line_text
from .base import BaseParser, ExtractedVariant
from .mg_equipment import parse_equipment

_MODEL_LINE_RE = re.compile(r"^(.+?)\s+OD\s+[\d\s]+K", re.MULTILINE)
_PRICE_RE = re.compile(r"\d[\d\s]*\s*Kč")
# Cyberster's own POHON value ("4×4") sits directly before CENA with
# nothing but a space between them - "4[space]1 759 000 Kč" reads to
# _PRICE_RE as one unbroken digit run, so the trailing "4" of "4×4" gets
# swept into the price. Masking it out (same length, so match offsets
# into the original text stay valid) before searching for the price
# avoids that; "4x4" (ASCII "x") is masked too in case a future document
# uses that spelling instead, matching `_AWD_RE`'s own two spellings in
# scripts/import_scraper_data.py.
_AWD_TOKEN_RE = re.compile(r"4[x×]4")
_KEEP_UPPERCASE = {"ZS", "HS", "EV", "PHEV"}


def _extract_model_name(pdf: pdfplumber.PDF) -> str:
    """Args:
        pdf: The opened price-list PDF.

    Returns:
        The model name from the cover page's own "<MODEL> OD <price> Kč"
        line, with the leading "MG" stripped and each remaining word
        title-cased except for `_KEEP_UPPERCASE` abbreviations - e.g.
        "MG4 EV URBAN OD 599 990 Kč" becomes "4 EV Urban". "unknown" if
        that line wasn't found.
    """
    cover_text = pdf.pages[0].extract_text() or ""
    match = _MODEL_LINE_RE.search(cover_text)
    if match is None:
        return "unknown"
    raw = match.group(1).strip()
    if raw.upper().startswith("MG"):
        raw = raw[2:].strip()
    words = [word if word.upper() in _KEEP_UPPERCASE else word.capitalize() for word in raw.split()]
    return " ".join(words) or "unknown"


def _looks_like_price_list_title(text: str) -> bool:
    """Args:
        text: The line(s) immediately above a "VÝBAVA ... MOTOR ..."
            header, own whitespace collapsed away first (see module
            docstring - the source PDF's own decorative "CENÍK" heading
            prints one letter per word).

    Returns:
        `True` for a genuine "CENÍK MG ..." price-list title with no
        "SKLADOV..." (stock-vehicles-only) word in it - `False` for a
        stock-only or seasonal-promo table, which should be skipped.
    """
    squashed = re.sub(r"\s+", "", text).upper()
    return "CENÍKMG" in squashed and "SKLADOV" not in squashed


def _trim_boundary(header_line: list[dict]) -> float:
    vybava_x0 = next(w["x0"] for w in header_line if w["text"].upper() == "VÝBAVA")
    motor_x0 = next(w["x0"] for w in header_line if w["text"].upper() == "MOTOR")
    return (vybava_x0 + motor_x0) / 2


def _nearest_trim(trim_headings: list[tuple[float, str]], row_top: float) -> str | None:
    """See OpelParser's own `_nearest_trim` - same idea: the heading whose
    own `top` is closest to `row_top`, correct for both a vertically-
    merged group heading and a same-line, single-row one (distance 0)."""
    if not trim_headings:
        return None
    return min(trim_headings, key=lambda pair: abs(pair[0] - row_top))[1]


def _classify_powertrain(engine: str) -> str:
    lowered = engine.lower()
    if "phev" in lowered:
        return "PHEV"
    if "hybrid+" in lowered:
        return "HEV"
    if "elektromotor" in lowered:
        return "EV"
    return "ICE"


class MgParser(BaseParser):
    brand = "mg"
    powertrain = "ICE"  # nominal default; the actual powertrain is per-row, see _classify_powertrain

    def parse(self, pdf_path: Path) -> list[ExtractedVariant]:
        """See module docstring for the row/trim shape and which tables
        on a multi-table page are skipped.

        Args:
            pdf_path: Local path to a downloaded MG price-list PDF.

        Returns:
            One `ExtractedVariant` per price row found under a genuine
            "CENÍK MG ..." table (see `_looks_like_price_list_title`),
            with `equipment` populated from MG's own "VÝBAVA" checkbox-
            matrix pages (see `mg_equipment.parse_equipment`).
        """
        variants: list[ExtractedVariant] = []

        with pdfplumber.open(pdf_path) as pdf:
            model = _extract_model_name(pdf)

            for page in pdf.pages:
                words = page.extract_words()
                lines = group_into_lines(words)
                header_indices = [
                    i
                    for i, line in enumerate(lines)
                    if {w["text"].upper() for w in line} >= {"VÝBAVA", "MOTOR"}
                ]
                if not header_indices:
                    continue

                for section, header_index in enumerate(header_indices):
                    title_text = line_text([word for line in lines[:header_index] for word in line])
                    if not _looks_like_price_list_title(title_text):
                        continue

                    trim_boundary = _trim_boundary(lines[header_index])
                    section_end = (
                        header_indices[section + 1] if section + 1 < len(header_indices) else len(lines)
                    )

                    trim_headings: list[tuple[float, str]] = []
                    row_lines: list[list[dict]] = []
                    for line in lines[header_index + 1 : section_end]:
                        leftmost = min(line, key=lambda word: word["x0"])
                        has_trim_word = leftmost["x0"] < trim_boundary
                        rest = [word for word in line if word["x0"] >= trim_boundary]
                        is_priced_row = bool(rest and _PRICE_RE.search(line_text(rest)))
                        # A trim heading is either bare (no `rest` at all)
                        # or self-contained with its own row (`rest` has a
                        # price) - a line whose `rest` is neither (e.g. a
                        # footnote like "*Akční cenové zvýhodnění platí na
                        # vybrané skladové vozy...", whose own leading "*"
                        # sits left of `trim_boundary` the same as a real
                        # trim word would) is prose, not a heading, and
                        # must not corrupt `_nearest_trim`'s own candidates.
                        if has_trim_word and (not rest or is_priced_row):
                            trim_text = line_text(
                                [word for word in line if word["x0"] < trim_boundary]
                            ).strip()
                            if trim_text:
                                trim_headings.append((line[0]["top"], trim_text))
                        if is_priced_row:
                            row_lines.append(rest)

                    for row in row_lines:
                        row_top = row[0]["top"]
                        full_text = line_text(row)
                        price_match = _PRICE_RE.search(_AWD_TOKEN_RE.sub("AWD", full_text))
                        if price_match is None:
                            continue
                        price = float(re.sub(r"\D", "", price_match.group(0)))
                        engine = full_text[: price_match.start()].strip()
                        if not engine:
                            continue
                        trim = _nearest_trim(trim_headings, row_top)
                        if trim is None:
                            continue

                        variants.append(
                            ExtractedVariant(
                                model=model,
                                trim=trim,
                                variant_name=f"{model} {trim} {engine}".strip(),
                                price=price,
                                currency="CZK",
                                source_page=page.page_number,
                                raw_text=full_text,
                                powertrain=_classify_powertrain(engine),
                            )
                        )

            # Trim order comes from the price rows just parsed above (a
            # single model per document, unlike Mazda's per-page
            # trims_by_model) - see mg_equipment.py's own module docstring
            # for why this also doubles as the mechanism that skips MG
            # HS's own equipment pages (their column count never matches
            # this trim list's length).
            trims: list[str] = []
            for variant in variants:
                if variant.trim not in trims:
                    trims.append(variant.trim)

            equipment_by_trim = parse_equipment(pdf, trims)
            for variant in variants:
                variant.equipment = equipment_by_trim.get(variant.trim, {})

        return variants

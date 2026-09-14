"""Parser for Hyundai price lists (Tucson, i20, Kona, Santa Fe — verified
against real PDF price lists downloaded 2026-08-28 from
dmassets.hyundai.com, model year 2027, effective from 2026-08-17).

Like Škoda (see skoda_ice.py), Hyundai's price table has no PDF grid, so
rows are reconstructed from word positions rather than `extract_text()` -
but the ambiguity here is different: Hyundai lists 3-4 separate price
columns per row (list price / promotional price / promotional price incl.
trade-in bonus / [HEV-PHEV sheets only] a fourth ex-VAT fleet price), e.g.

    1,6 T-GDI 4×2 110/150 6st. manuální 749 990 679 990 589 990

Naively splitting the trailing digits by thousands-separator spaces is
ambiguous for 7-digit prices (">999,999 Kč" splits into a 1-2 digit token
plus 3-digit continuations, e.g. "1 049 990" -> "1"/"049"/"990" - and nothing
in the text alone says where that number ends and the next price begins,
since a price could also legitimately start with a 3-digit token like
"944"). This is resolved positionally instead: only the FIRST (leftmost)
of the 3-4 price groups is needed here (the plain list price, "Standardní
cena s DPH" - same "list/standard price" convention as every other brand
in this scraper), and consecutive words belonging to the SAME price number
sit only ~1-3pt apart on the page, while the gap to the NEXT price column
is consistently 27pt or more (verified against real word x0/x1 coordinates
for all three fetched models) - so `_first_price_group` just walks the
trailing digit-only words and stops at the first gap bigger than
`_COLUMN_GAP_THRESHOLD`.

A line is a price row if its LAST word is a pure-digit token (with at
least 2 such trailing digit words, to rule out a stray single-digit
footnote marker) AND its prefix contains an engine displacement token
like "1,6" (`_DISPLACEMENT_RE`) - the digit check alone isn't enough,
since the cover portion of the same page also has marketing teaser
amounts that end the same way (e.g. "... Výkupní bonus 60 000 Kč", or
"Plug-in hybrid 6 967 Kč měs. vč. pojištění" - note this one even starts
with a real powertrain-line marker), each ending up as its own line after
`group_into_lines` groups by y-position. None of those ever contain a
displacement token, so the second check rules them out.

Powertrain is classified per-row from the leading marker/engine text, not
a class attribute (same principle as Volkswagen/Kia's mixed-powertrain
documents): plain rows have no marker ("1,6 T-GDI"), MHEV rows spell it
out inline ("1,6 CRDi MHEV 48V1"), and HEV/PHEV price lists (Tucson
"Hybrid a Plug-in", Santa Fe) prefix each row with "HEV*"/"PHEV" or
"Hybrid"/"Plug-in hybrid" depending on the model - see
`_classify_powertrain`.

Hyundai's cover page has no single clean "Brand Model" line to read the
model name from (unlike Škoda) - the closest per-model text varies by
document ("TUCSON Úvěr Hyunday Finance", "Nové SANTA FE Hybrid Operativní
leasing", ...). Since this parser is only ever registered for a known,
fixed set of Hyundai models (see config/sources.yaml), the model name is
recognized by keyword instead (`_MODEL_MARKERS`) rather than extracted
positionally.

Like Kia/Toyota (and unlike Škoda/VW), the cover page's "Ceník osobních
vozů platný od 17. srpna 2026" uses a written-out Czech month name, not
the "Platnost od D. M. RRRR" numeric format `_pdf_layout.extract_release_date`
matches - so `release_date` stays None here too, and VariantRepository
falls back to the download date."""
from __future__ import annotations

import re
from pathlib import Path

import pdfplumber

from ._pdf_layout import group_into_lines, line_text
from .base import BaseParser, ExtractedVariant
from .hyundai_equipment import parse_equipment

_TABLE_HEADER_MARKER = "Výbava a motor"
_COLUMN_GAP_THRESHOLD = 15.0  # pt; continuation gaps are ~1-3pt, real column gaps are 27pt+
# Every real price row has an engine displacement token ("1,6", "1,0", ...)
# somewhere in its prefix. Needed because "ends in >=2 digit words" alone
# also matches marketing teaser amounts on the cover portion of the
# price-table page (e.g. "... Výkupní bonus 60 000 Kč" / "Plug-in hybrid
# 6 967 Kč měs. vč. pojištění", split across lines by `group_into_lines`'s
# y-tolerance so the trailing digits end up on their own line) - those
# never contain a displacement token, even the ones that happen to start
# with a real powertrain-line marker like "Plug-in hybrid".
_DISPLACEMENT_RE = re.compile(r"^\d,\d$")

_MODEL_MARKERS = (
    ("SANTA FE", "Santa Fe"),
    ("TUCSON", "Tucson"),
    ("KONA", "Kona"),
    ("i30", "i30"),
    ("i20", "i20"),
)


def _extract_model(pdf: pdfplumber.PDF) -> str:
    """See module docstring for why this is a keyword lookup rather than
    positional extraction like Škoda/Kia/VW."""
    cover_text = pdf.pages[0].extract_text() or ""
    for marker, canonical in _MODEL_MARKERS:
        if marker in cover_text:
            return canonical
    return "unknown"


def _first_price_group(tokens: list[dict]) -> float | None:
    """Args:
        tokens: The trailing run of pure-digit words at the end of a price
            row (leftmost = the "Standardní cena s DPH" list price column).

    Returns:
        The leftmost price group's value, or `None` if `tokens` is empty.
        See module docstring for why the column boundary is found via the
        x-gap between words rather than by counting digits.
    """
    if not tokens:
        return None
    digits = tokens[0]["text"]
    prev_x1 = tokens[0]["x1"]
    for token in tokens[1:]:
        if token["x0"] - prev_x1 > _COLUMN_GAP_THRESHOLD:
            break
        digits += token["text"]
        prev_x1 = token["x1"]
    return float(digits) if digits.isdigit() else None


def _classify_powertrain(engine: str) -> str:
    engine_lower = engine.lower()
    if "plug-in" in engine_lower or "phev" in engine_lower:
        return "PHEV"
    if "mhev" in engine_lower:
        return "MHEV"
    if "hev" in engine_lower or "hybrid" in engine_lower:
        return "HEV"
    return "ICE"


class HyundaiParser(BaseParser):
    brand = "hyundai"
    powertrain = "ICE"  # nominal default; the actual powertrain is per-row, see _classify_powertrain

    def parse(self, pdf_path: Path) -> list[ExtractedVariant]:
        """See module docstring for Hyundai's row format and the
        positional technique used to isolate the list-price column.

        Args:
            pdf_path: Local path to a downloaded Hyundai price-list PDF.

        Returns:
            One `ExtractedVariant` per engine/trim row found across all
            pages with a `_TABLE_HEADER_MARKER` table (a document can have
            more than one, e.g. Santa Fe's HEV table on page 1 and PHEV
            table on page 8), `powertrain` classified per-row, `equipment`
            populated from the "Přehled hlavních prvků stupňů výbav"
            matrix (see `hyundai_equipment.parse_equipment`).
        """
        variants: list[ExtractedVariant] = []

        with pdfplumber.open(pdf_path) as pdf:
            model = _extract_model(pdf)
            equipment_by_trim = parse_equipment(pdf)

            for page in pdf.pages:
                text = page.extract_text() or ""
                if _TABLE_HEADER_MARKER not in text:
                    continue  # page without a price table (equipment, colors, legal copy, ...)

                lines = group_into_lines(page.extract_words())
                trim: str | None = None

                for line in lines:
                    if not line[-1]["text"].isdigit():
                        trim = line_text(line).strip()
                        continue

                    tail_start = len(line)
                    for i in range(len(line) - 1, -1, -1):
                        if not line[i]["text"].isdigit():
                            break
                        tail_start = i
                    prefix, numeric_tail = line[:tail_start], line[tail_start:]

                    if not prefix or len(numeric_tail) < 2:
                        continue  # not a real price row (e.g. a stray footnote digit)
                    if not any(_DISPLACEMENT_RE.match(w["text"]) for w in prefix):
                        continue  # a marketing teaser amount, not an engine/trim price row

                    price = _first_price_group(numeric_tail)
                    if price is None:
                        continue

                    engine = line_text(prefix).strip()
                    variants.append(
                        ExtractedVariant(
                            model=model,
                            trim=trim,
                            variant_name=" ".join(p for p in (model, trim, engine) if p),
                            price=price,
                            currency="CZK",
                            source_page=page.page_number,
                            raw_text=line_text(line),
                            powertrain=_classify_powertrain(engine),
                            equipment=equipment_by_trim.get(trim, {}),
                        )
                    )

        return variants

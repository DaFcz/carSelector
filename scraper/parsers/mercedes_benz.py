"""Parser for the Mercedes-Benz combined price list (verified against the
real "Souhrnný ceník osobních automobilů" PDF downloaded 2026-08-29 from
mercedes-benz.cz, effective from 27 May 2026).

Unlike every other brand here, one Mercedes-Benz document covers the ENTIRE
current lineup (74 pages: A-Class, CLA, GLA, GLB, EQA, C-Class, GLC, E-Class,
CLE, EQE, GLE, S-Class, EQS, GLS, G-Class, AMG GT, AMG SL, ...), not just the
models this scraper tracks (`config/sources.yaml`'s `models: [C-Class,
E-Class]` — see `monitors/discovery/mercedes_benz.py` for why discovery
doesn't need per-model fetches at all). So instead of assuming every page is
relevant like Kia/Toyota/Hyundai do, `parse` reads each page's own chapter
heading and only processes pages recognized by `_MODEL_MARKERS`, silently
skipping the ~65 pages covering other models. Sedan and estate ("kombi")
body styles are separate chapters in the source PDF (e.g. "Třídy C sedan"
vs "Třídy C kombi") and come out as distinct models here too, "C-Class
Estate"/"E-Class Estate" — not listed separately in `sources.yaml`'s
`models`, same principle as Hyundai's "Tucson Hybrid" (see that discoverer's
module docstring): the base entry names the nameplate, the parser is free
to split it further where the source document does.

Each variant is TWO physical table rows, not one (unlike every other brand
here), matching the "Cena ... bez DPH" / "... vč. DPH" two-line column
header:

    C 200 d 206.003 vznětový R4, 16V, mild hybrid 7,7 s 1993 automatický 9st. 4,5 - 5,2 1 045 000
    120+17(163+23)/380 Euro 6e 4x2 (Zadní) 230 km/h 9G-TRONIC 119 - 137 1 264 450

Row 1 (trim name + engine description, always starts with a letter) ends in
the list price EXCLUDING VAT; row 2 (power figures + emission class, always
starts with a digit) ends in the SAME price INCLUDING VAT (verified: row 2's
trailing number is always exactly row 1's × 1.21, the Czech VAT rate). Only
row 2's price is kept, matching this scraper's "price = the VAT-inclusive
consumer list price" convention used for every other brand (see hyundai.py's
module docstring) — `parse` pairs each row 1 with the row 2 immediately
following it via `_TYPE_CODE_RE`/starts-with-digit rather than storing both.

Row 2's trailing price is NOT simply "the trailing run of digit-only words"
the way row 1's is: the CO2 emissions range immediately before it is also
plain integers ("119 - 137 1 264 450" — "137" and the price's leading "1"
are both bare digit tokens with the "-" only breaking earlier), so naive
concatenation would swallow the range into the price. Resolved the same way
as Hyundai's multi-column ambiguity (see hyundai.py's module docstring):
consecutive digit words belonging to the SAME price sit ~2-3pt apart, while
the real column gap before the price is consistently 35pt+ (verified against
real word x0/x1 coordinates) — `_last_price_group` walks the trailing digit
run from the right and stops at the first gap past `_COLUMN_GAP_THRESHOLD`.
Row 1 has no such ambiguity (its fuel-consumption range uses decimal commas,
e.g. "4,5 - 5,2", which aren't pure-digit tokens), so its trailing run can't
capture more than the price itself.

Like Kia/Toyota/Hyundai (and unlike Škoda/VW), the cover page's "Platnost od
27. května 2026" uses a written-out Czech month name, not the "Platnost od
D. M. RRRR" numeric format `_pdf_layout.extract_release_date` matches - so
`release_date` stays None here too, and VariantRepository falls back to the
download date.
"""

from __future__ import annotations

import re
from pathlib import Path

import pdfplumber

from ._pdf_layout import group_into_lines, line_text
from .base import BaseParser, ExtractedVariant

_MODEL_MARKERS = (
    ("Třídy C sedan", "C-Class"),
    ("Třídy C kombi", "C-Class Estate"),
    ("Třídy E sedan", "E-Class"),
    ("Třídy E kombi", "E-Class Estate"),
)
_TABLE_HEADER_MARKERS = ("Typ vozidla", "kW(k)/kW(k)/Nm")
_TRIM_MARKERS = ("Vznětové motory", "Zážehové motory")  # diesel / petrol section headers
# A real row-1 line always has an internal type-designation code like
# "206.003" (3 digits, dot, 3 digits) right after the trim name - nothing
# else on the page (section headers, table/column headers, footnote
# markers) matches this, so it doubles as the "is this really a variant
# row" check, same role as Hyundai's _DISPLACEMENT_RE.
_TYPE_CODE_RE = re.compile(r"\d{3}\.\d{3}")
_COLUMN_GAP_THRESHOLD = 15.0  # pt; continuation gaps are ~2-3pt, the real column gap is 35pt+


def _page_model(text: str) -> str | None:
    """Returns the canonical model name for a page from its own chapter
    heading (repeated on every page of a chapter, so no cross-page state
    is needed - see module docstring), or `None` if this page belongs to
    a model this scraper doesn't track."""
    for marker, canonical in _MODEL_MARKERS:
        if marker in text:
            return canonical
    return None


def _trailing_digit_words(words: list[dict]) -> list[dict]:
    """Returns the trailing run of pure-digit words at the end of `words`
    (possibly empty)."""
    tail_start = len(words)
    for i in range(len(words) - 1, -1, -1):
        if not words[i]["text"].isdigit():
            break
        tail_start = i
    return words[tail_start:]


def _last_price_group(tail_words: list[dict]) -> float | None:
    """Args:
        tail_words: The trailing run of pure-digit words at the end of a
            row-2 line - may still contain an unrelated number group (the
            CO2 range) to its left, see module docstring.

    Returns:
        The RIGHTMOST digit group's value (row 2's own price column), or
        `None` if `tail_words` is empty.
    """
    if not tail_words:
        return None
    digits = tail_words[-1]["text"]
    next_x0 = tail_words[-1]["x0"]
    for word in reversed(tail_words[:-1]):
        if next_x0 - word["x1"] > _COLUMN_GAP_THRESHOLD:
            break
        digits = word["text"] + digits
        next_x0 = word["x0"]
    return float(digits) if digits.isdigit() else None


def _classify_powertrain(engine: str) -> str:
    if "plug-in hybrid" in engine:
        return "PHEV"
    if "mild hybrid" in engine:
        return "MHEV"
    if "hybrid" in engine:
        return "HEV"
    return "ICE"


class MercedesBenzParser(BaseParser):
    brand = "mercedes-benz"
    powertrain = "ICE"  # nominal default; the actual powertrain is per-row, see _classify_powertrain

    def parse(self, pdf_path: Path) -> list[ExtractedVariant]:
        """See module docstring for the two-physical-rows-per-variant
        format and why only a subset of the document's pages are parsed.

        Args:
            pdf_path: Local path to the downloaded combined Mercedes-Benz
                price-list PDF.

        Returns:
            One `ExtractedVariant` per variant row-pair found across the
            pages recognized by `_MODEL_MARKERS`, `powertrain` classified
            per-row.
        """
        variants: list[ExtractedVariant] = []

        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                text = page.extract_text() or ""
                model = _page_model(text)
                if model is None:
                    continue
                if not all(marker in text for marker in _TABLE_HEADER_MARKERS):
                    continue  # e.g. the "Cena (bez DPH) od" summary page for this chapter

                trim: str | None = None
                pending_engine: str | None = None
                pending_row1_text: str | None = None

                for line in group_into_lines(page.extract_words()):
                    tail = _trailing_digit_words(line)
                    if not tail:
                        line_str = line_text(line)
                        for marker in _TRIM_MARKERS:
                            if marker in line_str:
                                trim = marker
                                break
                        continue

                    if line[0]["text"][0].isdigit():
                        # Row 2 (power/emissions line) - pairs with the row-1
                        # engine text collected just before it.
                        if pending_engine is None:
                            continue
                        price = _last_price_group(tail)
                        if price is not None:
                            variants.append(
                                ExtractedVariant(
                                    model=model,
                                    trim=trim,
                                    variant_name=f"{model} {pending_engine}".strip(),
                                    price=price,
                                    currency="CZK",
                                    source_page=page.page_number,
                                    raw_text=f"{pending_row1_text} / {line_text(line)}",
                                    powertrain=_classify_powertrain(pending_engine),
                                )
                            )
                        pending_engine = None
                        pending_row1_text = None
                        continue

                    # Row 1 (trim name + engine description).
                    row1_text = line_text(line)
                    if _TYPE_CODE_RE.search(row1_text) is None:
                        continue  # not a real variant row (e.g. a footnote marker)
                    prefix = line[: len(line) - len(tail)]
                    pending_engine = line_text(prefix).strip()
                    pending_row1_text = row1_text

        return variants

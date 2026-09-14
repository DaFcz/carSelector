"""Parser for Mazda price lists (CX-5, 3, CX-30 — verified against real PDF
price lists downloaded 2026-08-29 from media-assets.mazda.eu, effective
2026-07/2026-08).

Mazda's price-list PDFs are a fundamentally different animal from every
other brand here: not a plain print-style price list, but a 25-38 page
"digital brochure" (clearly exported from an interactive web page - model
overview, trim walkthrough, colors, accessories, equipment matrix, THEN a
couple of pages of price tables) with a page size roughly double a normal
page's width. Two artifacts of that export process make naive
`page.extract_text()`/`page.extract_words()` unusable for the price pages:

1. **Off-page duplicate content.** Words extend from roughly -815pt to
   +815pt, while the visible page is only 0-842pt wide (`page.width`) -
   half the page's own words sit entirely outside the visible area,
   apparently a mirrored/duplicate copy of the whole layout. Excluded by
   only keeping chars with `0 <= x0` and `x1 <= page.width`.
2. **Overlapping same-position text runs, even within the visible half.**
   A large (16pt) section-anchor word (e.g. "CENÍK") and the small (6-8pt)
   real price-table text both start at nearly the same (top, x0) - close
   enough that `page.extract_words()`'s own word-boundary heuristic
   splices their characters together into one garbled token (verified via
   `page.chars`: two runs at the same top with overlapping x-ranges but
   different `size`). Filtering out characters with `size > 9` removes the
   anchor text (nothing in the actual price rows is that large) without
   needing to know what any specific anchor word says.

Even after both filters, a handful of REAL price rows come out doubled or
merged too - not because of the two problems above, but because Mazda
duplicates each row a second time nearby as a short "<trim> <list price>"
echo (no other columns), on a `top` typically 1-7pt below the real row's
own `top`. Unlike (1)/(2), this can't be filtered away by position or
font size alone - `_clean_lines` instead groups words by EXACT `top`
(rounded to 1 decimal - real distinct rows differ by >1pt, verified
against every row in the three fixtures) rather than the tolerance-based
`_pdf_layout.group_into_lines` every other parser uses (that tolerance is
exactly what would smear a real row and its echo together here). Each
resulting line is then validated by column count (see `_ROW_COLUMNS`
below) - matches keeps a fixed catalog price is the leftmost data column,
matching the "Cena" (list price incl. VAT) header - so the echo lines
(1 column) and any rare cross-row collision (verified: the fixtures have
a couple of pages where two rows land on the exact same rounded top,
producing more or fewer than `_ROW_COLUMNS` columns) both fail validation
and are silently dropped rather than risk extracting a wrong number -
same "skip rather than guess" precedent as every other parser here.

A real row (once cleanly isolated) reads e.g.:

    Prime-Line 875 900 Kč 51 000 Kč 824 900 Kč 824 900 Kč 4 999 Kč 5 161 Kč 12 343 Kč

i.e. trim name, then CENA (list price, incl. VAT per the page's own "Ceny
jsou uvedeny včetně DPH" footnote) / MODELOVÝ BONUS / AKČNÍ CENA / NEJNIŽŠÍ
CENA ZA POSLEDNÍCH 30 DNÍ / three monthly-payment columns. Only CENA (the
first column) is kept as `price` - the rest are a time-limited monthly
promotion, same "only the list price, not the promotional columns"
precedent as Kia (see kia.py's module docstring).

Trim levels vary by model (Prime-Line/Centre-Line/Exclusive-Line/Homura
for CX-5; those plus Takumi/Nagisa/Homura Plus for 3 and CX-30) and aren't
hardcoded - the trim name is just whatever text precedes the first price
column on a valid row. The preceding non-price line mentioning "SKYACTIV"
(e.g. "2.5L e-SKYACTIV G 2WD", "e-SKYACTIV G 140 K Manuální převodovka
6MT") is tracked as the engine/drivetrain context and folded into
`variant_name` (same "running section header" convention as Hyundai's
`trim`/Škoda's trim-level tracking) - AWD variants say so directly in that
text ("...G AWD"), which is enough for the shared `infer_drivetrain` regex
in `scripts/import_scraper_data.py` to classify them correctly without
this parser needing its own drivetrain field.

Model 3 (hatchback vs sedan) is the only one of the three with two body
styles - `_BODY_STYLE_MARKERS` reads the "CENY HATCHBACK"/"CENY SEDAN"
header repeated on every page of each section and comes out as "3" vs
"3 Sedan" respectively, same principle as Mercedes-Benz's sedan/estate
split (see mercedes_benz.py's module docstring) - CX-5 and CX-30 are
single-body-style and always keep the bare model name.

None of the three fixtures' price pages state "mild hybrid"/"MHEV" (unlike
Mercedes/Hyundai) even though Mazda's own marketing elsewhere calls this
generation's engines "M Hybrid" 48V-assisted - since that phrase isn't in
the price-table text itself, `powertrain` stays the neutral "ICE" default
here rather than inferring it from outside knowledge.

Like Kia/Toyota/Hyundai/Mercedes-Benz (and unlike Škoda/VW), the cover
page states a promotional order/delivery WINDOW ("Platí pro vozy objednané
od 1.7. a dodané do 30.9.2026"), not a single "Platnost od D. M. RRRR"
date - `_pdf_layout.extract_release_date` doesn't match this format, so
`release_date` stays None here too, and VariantRepository falls back to
the download date."""
from __future__ import annotations

import re
from pathlib import Path

import pdfplumber

from .base import BaseParser, ExtractedVariant
from .mazda_equipment import parse_equipment

_MODEL_LINE_RE = re.compile(r"MAZDA(.+)")
_BODY_STYLE_MARKERS = (("CENY HATCHBACK", ""), ("CENY SEDAN", " Sedan"))
_PRICE_GROUP_RE = re.compile(r"([\d\s\xa0]+)Kč")
_ROW_COLUMNS = 7  # Cena / Modelový bonus / Akční cena / Nejnižší cena / 3x měsíční splátka
_MAX_ANCHOR_FONT_SIZE = 9  # pt; real price-row text is 6-8pt, section-anchor duplicates are 10pt+


def _extract_model(pdf: pdfplumber.PDF) -> str:
    """The base nameplate is the cover page's first line, always "MAZDA
    <model>" but letter-spaced ("M A Z DA C X- 3 0") and sometimes
    prefixed with marketing copy ("ZCELA NOVÁ MAZDA CX-5") - collapsing
    all spaces first turns both into a clean "MAZDA<model>" to match
    against, regardless of the original spacing/kerning."""
    cover_text = pdf.pages[0].extract_text() or ""
    first_line = cover_text.strip().splitlines()[0] if cover_text.strip() else ""
    match = _MODEL_LINE_RE.search(first_line.replace(" ", ""))
    return match.group(1) if match else "unknown"


def _words_from_chars(chars: list[dict]) -> list[dict]:
    """Reconstructs words from `chars` already filtered to on-page and
    `size <= _MAX_ANCHOR_FONT_SIZE` (see module docstring) - characters on
    the same exact `top` (rounded to 1 decimal) within a small x-gap join
    into one word, same continuation-gap principle as every other
    positional parser here, just working from chars instead of
    `extract_words()` since the anchor-duplication problem (see module
    docstring) means words need reconstructing AFTER the size filter, not
    before."""
    chars = sorted(chars, key=lambda c: (round(c["top"], 1), c["x0"]))
    words: list[list[dict]] = []
    for char in chars:
        if words and abs(words[-1][-1]["top"] - char["top"]) < 0.3 and char["x0"] - words[-1][-1]["x1"] <= 2.0:
            words[-1].append(char)
        else:
            words.append([char])
    return [
        {"text": "".join(c["text"] for c in word), "x0": word[0]["x0"], "top": word[0]["top"]} for word in words
    ]


def _clean_lines(page: pdfplumber.page.Page) -> list[tuple[float, str]]:
    """Returns `(top, text)` for every line on `page`, grouped by EXACT
    `top` rather than the tolerance-based grouping in `_pdf_layout` - see
    module docstring for why a tolerance would smear a real row and its
    duplicate echo together here."""
    chars = [
        c
        for c in page.chars
        if 0 <= c["x0"] and c["x1"] <= page.width and c["size"] <= _MAX_ANCHOR_FONT_SIZE
    ]
    lines: dict[float, list[dict]] = {}
    for word in _words_from_chars(chars):
        lines.setdefault(round(word["top"], 1), []).append(word)
    return [
        (top, " ".join(w["text"] for w in sorted(words, key=lambda w: w["x0"])))
        for top, words in sorted(lines.items())
    ]


class MazdaParser(BaseParser):
    brand = "mazda"
    powertrain = "ICE"  # see module docstring for why this isn't inferred per-row

    def parse(self, pdf_path: Path) -> list[ExtractedVariant]:
        """See module docstring for the row format, the de-duplication
        this needs, and why only the list-price column is kept.

        Args:
            pdf_path: Local path to a downloaded Mazda price-list PDF.

        Returns:
            One `ExtractedVariant` per validated price row found across
            all pages, `model` split into a body-style-specific name where
            the document has more than one (currently just Mazda3), each
            with `equipment` populated from the VÝBAVA pages (see
            `mazda_equipment.parse_equipment`).
        """
        variants: list[ExtractedVariant] = []

        with pdfplumber.open(pdf_path) as pdf:
            base_model = _extract_model(pdf)

            for page in pdf.pages:
                page_text = page.extract_text() or ""
                # Single-body-style models (CX-5, CX-30) never match either marker on any
                # page, so `model` just stays `base_model` for them - see module docstring.
                body_style_suffix = next(
                    (suffix for marker, suffix in _BODY_STYLE_MARKERS if marker in page_text.upper()), ""
                )
                model = base_model + body_style_suffix

                engine: str | None = None
                for top, text in _clean_lines(page):
                    if "SKYACTIV" in text.upper() and _PRICE_GROUP_RE.search(text) is None:
                        engine = text.strip()
                        continue

                    groups = _PRICE_GROUP_RE.findall(text)
                    if len(groups) != _ROW_COLUMNS:
                        continue  # echo duplicate (1 group) or a rare cross-row collision - see module docstring

                    trim = text[: text.index(groups[0])].strip()
                    if not trim or any(ch.isdigit() for ch in trim):
                        continue  # the echo/collision case can also leave no (or a numeric) prefix

                    price_text = groups[0].replace(" ", "").replace("\xa0", "")
                    if not price_text.isdigit():
                        continue

                    variants.append(
                        ExtractedVariant(
                            model=model,
                            trim=trim,
                            variant_name=" ".join(p for p in (model, trim, engine) if p),
                            price=float(price_text),
                            currency="CZK",
                            source_page=page.page_number,
                            raw_text=text,
                            powertrain=self.powertrain,
                        )
                    )

            # Trim names/order per model come from the price rows just
            # parsed above (first-seen order = left-to-right column order
            # on a VÝBAVA page too, verified against all three fixtures),
            # not from re-parsing an equipment page's own header - see
            # mazda_equipment.py's module docstring for why (a genuine
            # two-word trim, Mazda3's "Homura Plus", can't be told apart
            # from two one-word trims by splitting header text alone).
            trims_by_model: dict[str, list[str]] = {}
            for variant in variants:
                trims_by_model.setdefault(variant.model, [])
                if variant.trim not in trims_by_model[variant.model]:
                    trims_by_model[variant.model].append(variant.trim)

            equipment_by_model = parse_equipment(pdf, trims_by_model)
            for variant in variants:
                variant.equipment = equipment_by_model.get(variant.model, {}).get(variant.trim, {})

        return variants

        return variants

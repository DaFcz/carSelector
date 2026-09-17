"""Parser for Peugeot's per-model "Ceník, výbava a technické údaje" price
lists (verified against real PDFs downloaded 2026-09-13 from
peugeot.ecpaper.cz, effective September 2026 - see
scraper/tests/fixtures/peugeot_*.pdf). Covers the current CZ personal-car
lineup with a working price list: 208, 2008, 308 SW, 3008, 408, 5008,
Rifter. Peugeot is a fellow Stellantis brand alongside Opel, and its price
table reads like a simplified version of Opel's own column grid (see
OpelParser's module docstring) - trim/engine/CO2/list price/discount/
promo price, one row per engine - but without Opel's own column-boundary
pitfalls, so this parser is line-sequence based instead of column-position
based (see below for why that's both simpler and more robust here).

Two personal-car nameplates are NOT covered: the plain "308" hatchback's
own "Ceník a tech. data" link on peugeot.cz is dead (404s back to
ecpaper.cz's generic customer/catalogs landing page, verified 2026-09-13
both via `requests` and a real browser) - only "308 SW" (the wagon) has a
working document, so plain "308" is simply omitted, same convention as
CUPRA's own stock-only/not-yet-on-sale omissions (see discovery/cupra.py's
module docstring). Traveller uses a completely different document
structure (a "Ceník Furgon"-style flat list with excl./incl.-VAT price
pairs, closer to Expert/Boxer's own commercial-vehicle documents than to
the personal-car grid every other model here uses) and isn't covered yet.
Expert/Partner/Boxer commercial vehicles are out of scope, same "personal
cars only" convention as every other brand here.

Each row is anchored by its own 16-character alnum product code (e.g.
"1PP2A5HJLKC02PH2" - the same LCDV-style code Opel's own documents use,
unsurprising for a fellow Stellantis brand) on its own physical line
shortly before or after the row's own price line - "before" for most rows
but not all (verified on 3008's own document: a row with no discount/
promo squeezes trim + engine + price onto ONE line and pushes the CO2
figure onto a second line by itself, reversing the usual order). Unlike
Opel, this parser doesn't classify words into columns by x-position at
all - Peugeot's own price line packs the CO2 figure, list price, discount
and promo price tightly together with comparatively narrow, uniform-width
numeric tokens (unlike Opel's wide text tokens like "(81kW/110k)"), but a
wide DISCOUNT value could still in principle bleed across a fixed column
boundary the same way Opel's did. Sidestepping column boundaries (and the
row's own physical line layout) entirely avoids both of those problems:
`_build_variant` finds every "<digits> Kč" run in the row's own combined
text regardless of which line it landed on (the first is always the list
price - discount and promo, when present, are read then discarded, same
convention as every other brand's own promotional column here) and the
"<digits> g" CO2 figure the same way, and builds the engine description
from whatever text is left after removing both - which is how a range
figure like "Dojezd: 362 km" that shares a line with the price ends up
correctly kept as part of the engine text instead of discarded with it.

Trim headings aren't a separate merged cell like Opel's own (see
OpelParser's docstring point 1) - they're printed inline on the very same
line as that trim's first engine row (e.g. "STYLE Turbo 100 MAN6" is ONE
physical line, "STYLE" left of the VÝBAVA/MOTOR column boundary, "Turbo
100 MAN6" right of it), so a trim heading is simply carried forward as
state until the next one is seen - no distance-based assignment needed.

Rifter's own document is the one exception with a real wrinkle: it covers
FOUR sub-tables in one document ("RIFTER", "RIFTER LONG", "RIFTER S
HOMOLOGACÍ N1" and "RIFTER LONG S HOMOLOGACÍ N1", each with its own full
VÝBAVA/MOTOR/... header and row block - verified against a rendered page
image), the same "one document, several sub-tables" shape CUPRA's Leon
"Tribe" special edition uses (see CupraParser's own docstring) rather than
Astra's own separate-HB/ST-documents shape. Each header found on a page
starts its own row-scanning section (up to the next header or the end of
the page); the line immediately before a header, when it's just the
model's own name with an optional suffix, supplies that section's `model`
value (the suffix, if any, appended to the base model name) rather than
being read as a stray trim heading - UNLESS that suffix is an "N1"
homologation one, which is skipped outright: N1 is the EU light-
commercial-vehicle type-approval category (the same tax/registration
classification Combo/Vivaro/Movano's own exclusion above is about, not a
different physical car), so both "S HOMOLOGACÍ N1" sections are out of
scope for the same reason.

Powertrain is classified from the engine column's own text: "Plug-in"
(checked first) is PHEV; "Hybrid" otherwise is Peugeot/Stellantis's own
48V mild-hybrid tech (same tech, same convention as OpelParser's own
"Hybrid" - MHEV, not HEV); "Elektromotor"/"Electric" is EV; everything
else (Turbo/BlueHDi/Diesel petrol and diesel engines) is plain ICE, with
`scripts/import_scraper_data.py`'s own diesel regex needing a new "HDi"
alternative for BlueHDi's own diesel badge (not covered by the existing
TDI/CRDI/CDTI/BMW-suffix patterns).

Like every other brand here except Škoda/VW, the cover page carries no
usable release date in `_pdf_layout.extract_release_date`'s expected
format (the closest text is "Ceny platné na skladové vozy od D. M. RRRR
do D. M. RRRR", a closed campaign window like CUPRA's/Renault's/Opel's
own gap - see their module docstrings), so `release_date` stays None;
VariantRepository falls back to the download date."""
from __future__ import annotations

import re
from pathlib import Path

import pdfplumber

from ._pdf_layout import group_into_lines, line_text
from .base import BaseParser, ExtractedVariant
from .peugeot_equipment import parse_equipment as _parse_equipment_pages

_KNOWN_MODELS = ("308 SW", "2008", "208", "3008", "408", "5008", "Rifter")
_CODE_RE = re.compile(r"^[A-Z0-9]{16}$")
_PRICE_RE = re.compile(r"\d[\d\s]*\s*Kč")
_CO2_RE = re.compile(r"\d+\s*g\b")
_HEADER_TOP_WINDOW = 10.0  # pt; the header's own 3 physical sub-lines are ~5pt apart


def _extract_model_name(pdf: pdfplumber.PDF) -> str:
    """Args:
        pdf: The opened price-list PDF.

    Returns:
        The canonical model name matched against `_KNOWN_MODELS` (a
        substring match against the cover page, longest name first so
        "3008"/"2008" can't be mistaken for one another - though in
        practice none of these names are substrings of each other), or
        "unknown" if none matched.
    """
    cover_text = re.sub(r"\s+", " ", pdf.pages[0].extract_text() or "").upper()
    for model in sorted(_KNOWN_MODELS, key=len, reverse=True):
        if model.upper() in cover_text:
            return model
    return "unknown"


def _is_header_line(line: list[dict]) -> bool:
    texts = {w["text"].upper() for w in line}
    return "VÝBAVA" in texts and "MOTOR" in texts


def _trim_boundary(header_line: list[dict]) -> float:
    """Args:
        header_line: A line `_is_header_line` matched.

    Returns:
        The x-position midway between the VÝBAVA and MOTOR header words -
        anything left of it on a data line is a trim heading, anything
        right of it is engine/price text (see module docstring).
    """
    vybava_x0 = next(w["x0"] for w in header_line if w["text"].upper() == "VÝBAVA")
    motor_x0 = next(w["x0"] for w in header_line if w["text"].upper() == "MOTOR")
    return (vybava_x0 + motor_x0) / 2


def _section_label(lines: list[list[dict]], header_index: int) -> str:
    """Args:
        lines: The whole page's lines (see `_pdf_layout.group_into_lines`).
        header_index: Index into `lines` of the line `_is_header_line`
            matched (the "VÝBAVA MOTOR ..." middle sub-line of a 3-line
            header block, see module docstring).

    Returns:
        The text of the line just before this header BLOCK - not simply
        `lines[header_index - 1]`, which is usually still part of the same
        header's own wrapped sub-lines (e.g. "EMISE CO AKČNÍ AKČNÍ" one
        line above "VÝBAVA MOTOR ..."). Walks back past every line within
        `_HEADER_TOP_WINDOW` of the next one first, landing on the actual
        preceding content line - a body-length label like "RIFTER"/
        "RIFTER LONG" for Rifter's own two-section document, or ordinary
        marketing copy for every other (single-section) document.
    """
    block_start = header_index
    while block_start > 0 and lines[block_start][0]["top"] - lines[block_start - 1][0]["top"] < _HEADER_TOP_WINDOW:
        block_start -= 1
    return line_text(lines[block_start - 1]).strip() if block_start > 0 else ""


def _classify_powertrain(engine: str) -> str:
    lowered = engine.lower()
    if "plug-in" in lowered:
        return "PHEV"
    if "hybrid" in lowered:
        return "MHEV"
    if "elektromotor" in lowered or "electric" in lowered:
        return "EV"
    return "ICE"


def _build_variant(model: str, trim: str, pending: list[list[dict]], page_number: int) -> ExtractedVariant | None:
    """Args:
        model: This section's own model name (base model, plus Rifter's
            own body-length suffix when present - see module docstring).
        trim: The trim heading currently in effect for this row.
        pending: The lines collected between the previous row (or trim
            heading) and this row's own product-code line - one or more
            engine/range description lines followed by the row's own
            price line (see module docstring for why the price is found
            by regex rather than by column position).
        page_number: 1-based PDF page this row was read from.

    Returns:
        The `ExtractedVariant` for this row, or `None` if either the
        engine text or the price couldn't be resolved (an incomplete or
        misread row is skipped rather than stored with bad data).
    """
    if not pending:
        return None
    full_text = line_text([w for line in pending for w in line])

    price_matches = list(_PRICE_RE.finditer(full_text))
    if not price_matches:
        return None
    price = float(re.sub(r"\D", "", price_matches[0].group(0)))

    # Strip the price/discount/promo Kč run(s) and the CO2 "<N> g" figure
    # out of the row's own text to get the engine description, rather than
    # assuming they always land on one particular physical line: some rows
    # (verified on 3008's own document) pack trim + engine + price onto
    # ONE line and push the CO2 figure onto its own line right after,
    # reversing the usual "engine line(s), then the price line" order.
    spans = sorted(m.span() for m in price_matches)
    co2_match = _CO2_RE.search(full_text)
    if co2_match is not None:
        spans.append(co2_match.span())
    spans.sort()
    engine_parts = []
    cursor = 0
    for start, end in spans:
        engine_parts.append(full_text[cursor:start])
        cursor = end
    engine_parts.append(full_text[cursor:])
    engine = re.sub(r"\s+", " ", "".join(engine_parts)).strip()
    if not engine:
        return None

    return ExtractedVariant(
        model=model,
        trim=trim,
        variant_name=f"{model} {trim} {engine}".strip(),
        price=price,
        currency="CZK",
        source_page=page_number,
        raw_text=full_text,
        powertrain=_classify_powertrain(engine),
    )


class PeugeotParser(BaseParser):
    brand = "peugeot"
    powertrain = "ICE"  # nominal default; the actual powertrain is per-row, see _classify_powertrain

    def parse(self, pdf_path: Path) -> list[ExtractedVariant]:
        """See module docstring for the row-sequence shape (trim heading
        inline with its first row, engine/range text, a price line, a
        product-code line) and how Rifter's own two body-length
        sub-tables are each read as their own section.

        Args:
            pdf_path: Local path to a downloaded Peugeot price-list PDF.

        Returns:
            One `ExtractedVariant` per price row found on any page with a
            "VÝBAVA ... MOTOR ..." header.
        """
        variants: list[ExtractedVariant] = []

        with pdfplumber.open(pdf_path) as pdf:
            base_model = _extract_model_name(pdf)

            for page in pdf.pages:
                words = page.extract_words()
                lines = group_into_lines(words)
                header_indices = [i for i, line in enumerate(lines) if _is_header_line(line)]
                if not header_indices:
                    continue

                for section, header_index in enumerate(header_indices):
                    trim_boundary = _trim_boundary(lines[header_index])

                    preceding_text = _section_label(lines, header_index)
                    if "HOMOLOGAC" in preceding_text.upper():
                        continue  # N1 (light-commercial) homologation table - out of scope, see module docstring

                    model = base_model
                    if preceding_text.upper().startswith(base_model.upper()):
                        suffix = preceding_text[len(base_model) :].strip()
                        model = f"{base_model} {suffix}".strip()

                    section_end = (
                        header_indices[section + 1] if section + 1 < len(header_indices) else len(lines)
                    )

                    current_trim: str | None = None
                    pending: list[list[dict]] = []
                    for line in lines[header_index + 1 : section_end]:
                        leftmost = min(line, key=lambda word: word["x0"])
                        if leftmost["x0"] < trim_boundary and leftmost["text"].isalpha():
                            current_trim = line_text(
                                [word for word in line if word["x0"] < trim_boundary]
                            ).strip()
                            rest = [word for word in line if word["x0"] >= trim_boundary]
                            pending = [rest] if rest else []
                            continue

                        if len(line) == 1 and _CODE_RE.match(line[0]["text"]):
                            if current_trim is not None:
                                variant = _build_variant(model, current_trim, pending, page.page_number)
                                if variant is not None:
                                    variants.append(variant)
                            pending = []
                            continue

                        pending.append(line)

            trims_by_model: dict[str, list[str]] = {}
            for variant in variants:
                trims_by_model.setdefault(variant.model, [])
                if variant.trim not in trims_by_model[variant.model]:
                    trims_by_model[variant.model].append(variant.trim)

            equipment_by_model = _parse_equipment_pages(pdf, trims_by_model)
            for variant in variants:
                per_trim = equipment_by_model.get(variant.model, {})
                equipment, surcharge = per_trim.get(variant.trim, ({}, {}))
                variant.equipment = equipment
                variant.equipment_surcharge = surcharge

        return variants

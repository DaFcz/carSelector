"""Parser for CUPRA's per-model "Ceník" price lists (verified against real
PDFs downloaded 2026-09-12 from cupraofficial.cz's asset CDN, effective
26 May-17 August 2026 depending on model — see scraper/tests/fixtures/
cupra_*.pdf). Covers Leon, Leon Sportstourer, Formentor, Terramar, Born
and Raval - the full current CZ lineup with a price list at all (Ateca is
sold as stock-only with no price-list PDF of its own, and Tavascan has no
CZ page yet at all - see discovery/cupra.py's module docstring).

Unlike Ford's genuine trim x engine price matrix, CUPRA's price list is a
plain one-column list, much closer to Kia's: a trim heading ("CUPRA", "VZ",
"VZ Extreme", or an "Akční model <name>" special edition), then one row per
engine underneath it, e.g.:

    1.5 TSI 150k 110/150 Manuální 6 st. 5.8 l/100km 132 g/km 809 900 Kč

engine, power ("kW/hp"), transmission, combined consumption, combined CO2,
then the list price ("Cena s DPH") - kept as `price`, matching every other
brand's "list price, not a promotional one" convention. Some rows (Leon
Sportstourer, Terramar) carry a second, discounted "Akční cena s paketem"
price after the first - read then discarded, same convention.

`page.extract_text()` visually scrambles several of these rows (verified
against a rendered page image, not just extracted text, for Terramar):
the consumption figure sits at a slightly different y-offset than the rest
of its own row (apparently vertically centered against a taller row height
than the other columns need), which extract_text()'s own line-breaking
heuristic - tuned tighter than word position alone - splits onto what
looks like its own line. `_pdf_layout.group_into_lines` (tolerance 4pt)
still merges these correctly, because the actual y-gap involved (~3pt) is
well inside that tolerance - same technique Škoda's and Dacia's parsers
use for their own layout quirks, see this module's own verification notes
in scraper/tests/test_cupra_parser.py.

Row shape is otherwise a single regex (`_ROW_RE`), anchored on the
power figure ("110/150") since it's the one token no other field's text
can be mistaken for - everything before it is `engine` (any word count:
"1.5 TSI 150k", "e-HYBRID 204k DSG", "58 kWh", "55,2 kWh 210 k"), and
everything between it and the consumption figure is `transmission`
("Manuální 6 st.", "Aut. DSG7", "Automatická"). A row missing power/
transmission/consumption/CO2 entirely (Born's base 50 kWh trim, in the
source PDF itself, verified against the rendered page) simply doesn't
match `_ROW_RE` and is skipped - a known gap in CUPRA's OWN published
price list, not something to guess a spec for.

Price formatting is inconsistent even across CUPRA's own documents -
Leon/Terramar/Raval space-separate thousands ("1 179 900"), Formentor/Leon
Sportstourer comma-separate them ("1,094,900") - `_parse_price` strips
both, safe since no field here ever needs a fractional-Kč value.

Powertrain is classified from the row's own text: a consumption unit of
"kWh" (vs. "l") -> EV (Born/Raval); "e-HYBRID" in the engine name -> PHEV
(CUPRA's plug-in hybrid); "eTSI" -> MHEV (VW Group's 48V mild-hybrid
petrol engines - same classification Kia/Toyota/Hyundai's parsers already
give their own mild hybrids); everything else -> ICE.

CUPRA's own disclaimer text - "Platnost od D. M. RRRR" or "Platnost od
DD.MM.RRRR" (both forms seen across these six documents) - would actually
satisfy `_pdf_layout.extract_release_date`'s pattern (its `\\s*` between
day/month/year tolerates either spacing), but that text sits on the price-
table page (page 2), not the cover page `extract_release_date` reads
(`pdf.pages[0]` only, hardcoded - CUPRA's own cover is just the model name
over a decorative "Model Configuration" button, see
`_extract_model_name`). So `release_date` stays None here too, for a
different reason than every other brand added so far (a wrong page, not a
wrong date format) - VariantRepository falls back to the download date."""
from __future__ import annotations

import re
from pathlib import Path

import pdfplumber

from ._pdf_layout import group_into_lines, line_text
from .base import BaseParser, ExtractedVariant
from .cupra_equipment import parse_colors, parse_standard_equipment

# Longest name first, so "Leon Sportstourer"'s cover page isn't misread as plain "Leon".
_KNOWN_MODELS = ("Leon Sportstourer", "Leon", "Formentor", "Terramar", "Born", "Raval")
_END_OF_TABLE_MARKER = "Uvedené částky jsou ceny doporučené"
_ROW_RE = re.compile(
    r"^(?P<engine>.+?)\s+(?P<power>\d+/\d+)\s+(?P<transmission>.+?)\s+"
    r"(?P<consumption>[\d.,]+)\s*(?P<consumption_unit>l|kWh)?/100km\s+"
    r"(?P<co2>\d+)\s*g/km\s+"
    r"(?P<price>[\d\s,]+?)\s*Kč(?:\s+(?P<promo_price>[\d\s,]+?)\s*Kč)?\s*$"
)


def _extract_model_name(pdf: pdfplumber.PDF) -> str:
    """Args:
        pdf: The opened price-list PDF.

    Returns:
        The canonical model name matched against `_KNOWN_MODELS` (a
        substring match, not a specific cover-page line - the cover's own
        layout order varies: Raval's reads "NOVÝ"/"RAVAL" on two lines
        with a marketing prefix, Leon Sportstourer's reads "LEON"/
        "SPORTSTOURER" on two lines with neither prefixed, both around a
        decorative reversed-text "Model"/"Configuration" button whose
        position relative to the model name also isn't fixed), or
        "unknown" if none matched.
    """
    cover_text = (pdf.pages[0].extract_text() or "").upper()
    cover_text = re.sub(r"\s+", " ", cover_text)
    for model in _KNOWN_MODELS:
        if model.upper() in cover_text:
            return model
    return "unknown"


def _is_header_line(line: list[dict]) -> bool:
    texts = {w["text"] for w in line}
    return "Motor" in texts and "Převodovka" in texts


def _parse_price(text: str) -> float:
    return float(text.replace(" ", "").replace(",", ""))


def _resolve_equipment(trim: str, equipment_by_trim: dict[str, dict[str, str]]) -> dict[str, str]:
    """Args:
        trim: A price-table trim name (`ExtractedVariant.trim`).
        equipment_by_trim: `parse_standard_equipment`'s own result, keyed
            by the SÉRIOVÁ VÝBAVA page's own heading text.

    Returns:
        That trim's equipment, or `{}` if genuinely uncovered. Handles
        one verified naming split, not a general fuzzy match: Terramar's
        price table calls its special editions "Tribe Edition"/"Tribe VZ
        Edition", but the SAME document's own SÉRIOVÁ VÝBAVA headings
        drop the marketing suffix ("Tribe"/"Tribe VZ" - see
        cupra_equipment.py's own module docstring for how a bare heading
        vs. a "<TRIM> /navíc oproti výbavě <OTHER>" one is told apart;
        neither form ever restates "Edition"). Raval's own "Akční model
        ROOKIE" has no such alias - it has no SÉRIOVÁ VÝBAVA section
        under ANY name - so it stays a genuine `{}` gap, not guessed.
    """
    if trim in equipment_by_trim:
        return equipment_by_trim[trim]
    if trim.endswith(" Edition"):
        return equipment_by_trim.get(trim[: -len(" Edition")], {})
    return {}


def _classify_powertrain(engine: str, consumption_unit: str | None) -> str:
    if consumption_unit is not None and consumption_unit.lower() == "kwh":
        return "EV"
    lowered = engine.lower()
    if "e-hybrid" in lowered:
        return "PHEV"
    if "etsi" in lowered:
        return "MHEV"
    return "ICE"


def _parse_row(line: list[dict], model: str, trim: str | None, source_page: int) -> ExtractedVariant | None:
    """Args:
        line: One line's words from the price table (a data row, a trim
            heading, or leftover legal text below the table).
        model: This document's model name (from `_extract_model_name`).
        trim: The trim currently in effect (from the last non-row line
            seen, which `parse` treats as a trim heading) - `None` if no
            heading has been seen yet on this page.
        source_page: 1-based page number `line` was read from.

    Returns:
        The row's `ExtractedVariant`, or `None` if `line` doesn't match
        `_ROW_RE` (a trim heading, the legal disclaimer, or a row with a
        spec CUPRA's own price list doesn't state - see module docstring)
        or no trim heading has been seen yet.
    """
    if trim is None:
        return None
    match = _ROW_RE.match(line_text(line))
    if match is None:
        return None

    engine = match.group("engine").strip()
    price = _parse_price(match.group("price"))
    variant_name = f"{model} {trim} {engine}".strip()

    return ExtractedVariant(
        model=model,
        trim=trim,
        variant_name=variant_name,
        price=price,
        currency="CZK",
        source_page=source_page,
        raw_text=line_text(line),
        powertrain=_classify_powertrain(engine, match.group("consumption_unit")),
    )


class CupraParser(BaseParser):
    brand = "cupra"
    powertrain = "ICE"  # nominal default; the actual powertrain is per-row, see _classify_powertrain

    def parse(self, pdf_path: Path) -> list[ExtractedVariant]:
        """See module docstring for the row shape and known gaps.

        Args:
            pdf_path: Local path to a downloaded CUPRA price-list PDF.

        Returns:
            One `ExtractedVariant` per price row found on the page(s)
            with a "Motor ... Převodovka ..." header.
        """
        variants: list[ExtractedVariant] = []

        with pdfplumber.open(pdf_path) as pdf:
            model = _extract_model_name(pdf)

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

                    variant = _parse_row(line, model, trim, page.page_number)
                    if variant is not None:
                        variants.append(variant)
                    elif "Kč" not in text:
                        # A genuine trim heading ("CUPRA", "VZ Extreme",
                        # "Akční model REBORN", ...) - never mentions a
                        # price. A line that DOES mention "Kč" but still
                        # didn't match _ROW_RE is an incomplete data row
                        # (e.g. Born's base 50 kWh trim - price with no
                        # power/transmission/consumption/CO2 given, see
                        # module docstring) - skipped without touching
                        # `trim`, not mistaken for a new heading.
                        trim = text.strip()

            trims_in_order: list[str] = []
            for variant in variants:
                if variant.trim not in trims_in_order:
                    trims_in_order.append(variant.trim)

            equipment_by_trim = parse_standard_equipment(pdf)
            colors_by_trim = parse_colors(pdf, trims_in_order)

            for variant in variants:
                equipment = dict(_resolve_equipment(variant.trim, equipment_by_trim))
                surcharge: dict[str, float] = {}
                trim_colors, trim_color_surcharge = colors_by_trim.get(variant.trim, ({}, {}))
                # Colors have no dedicated place in this schema (see
                # base.py's ExtractedVariant) - folded into the same
                # equipment/equipment_surcharge fields every other item
                # already uses, same convention storage/README.md and
                # every other brand's own paint-as-equipment items here
                # (e.g. peugeot_equipment.py's own priced paint options)
                # already follow.
                equipment.update(trim_colors)
                surcharge.update(trim_color_surcharge)
                variant.equipment = equipment
                variant.equipment_surcharge = surcharge

        return variants

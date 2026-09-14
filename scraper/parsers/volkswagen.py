"""Parser for Volkswagen price lists (verified against a real Golf price
list, downloaded 2026-07-19, effective from 2026-04-01).

Unlike Škoda (a positional table without a grid, see skoda_ice.py), the
VW price list is line-based text — `pdfplumber.extract_text()` gives one
line per variant, so it can be parsed with a regex instead of
reconstructing columns from word positions:

    1,5 TSI / 85 kW DA12BX04 Benzin 85/115 Manuální 6 st. Přední 560 248 Kč 677 900 Kč

A line that doesn't match this pattern (and isn't blank or the "Zdvihový
objem..." header) is a trim-level name (e.g. "Life", "Style", "R-Line")
— it applies to all following data rows until the next such line. The
first group of rows (without its own heading) belongs to the trim named
the same as the model (e.g. "Golf").

Unlike Škoda (a separate parser for ICE/EV), a single VW price list
contains combustion/mild-hybrid/plug-in-hybrid variants mixed together —
so the powertrain isn't determined from a class attribute, but per row
based on the fuel text (see `_classify_powertrain`).

The price is "Cena s DPH" ("price incl. VAT", the end-customer price),
same principle as for Škoda. The line is stored unchanged in `raw_text`
so it can be verified against the PDF."""
from __future__ import annotations

import re
from pathlib import Path

import pdfplumber

from .base import BaseParser, ExtractedVariant
from .vw_equipment import parse_standard_equipment

_ROW_RE = re.compile(
    r"^(?P<engine>.+?)\s*/\s*(?P<engine_kw>\d+)\s*kW\s+"
    r"(?P<code>\S+)\s+"
    r"(?P<fuel>.+?)\s+"
    r"(?P<power_kw>\d+)/(?P<power_hp>\d+)\s+"
    r"(?P<transmission>.+?)\s+"
    r"(?P<drivetrain>Přední|Zadní|Všech kol)\s+"
    r"(?P<price_novat>[\d ]+?)\s*Kč\s+"
    r"(?P<price_vat>[\d ]+?)\s*Kč$"
)
_MODEL_HEADER_RE = re.compile(r"^(?P<model>.+?)\s+Ceník\s+\d+$")
_TABLE_HEADER_MARKER = "Cena bez DPH"


def _classify_powertrain(fuel: str) -> str:
    fuel_lower = fuel.lower()
    if "plug-in" in fuel_lower:
        return "PHEV"
    if "hybrid" in fuel_lower:
        return "MHEV"
    return "ICE"


class VolkswagenParser(BaseParser):
    brand = "volkswagen"
    powertrain = "ICE"  # nominal default; the actual powertrain is per-row, see _classify_powertrain

    def parse(self, pdf_path: Path) -> list[ExtractedVariant]:
        """See module docstring for Volkswagen ICE/MHEV/PHEV's row format.

        Args:
            pdf_path: Local path to a downloaded VW price-list PDF.

        Returns:
            One `ExtractedVariant` per engine/trim row found across pages
            with a price table, `powertrain` classified per-row via
            `_classify_powertrain`, `equipment` populated from the
            "Sériová Výbava" pages (see `vw_equipment.parse_standard_equipment`).
        """
        variants: list[ExtractedVariant] = []

        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                text = page.extract_text() or ""
                if _TABLE_HEADER_MARKER not in text:
                    continue  # page without a price table (equipment, technical data, ...)

                lines = text.splitlines()
                model_match = _MODEL_HEADER_RE.match(lines[0].strip())
                model = model_match.group("model") if model_match else lines[0].strip()
                # the marketing word "Nový " ("New", e.g. "Nový T-Roc Ceník 2")
                # would otherwise make the model differ from the name in sources.yaml
                model = model.removeprefix("Nový ").strip()

                trim: str | None = None
                for line in lines[1:]:
                    line = line.strip()
                    if not line or "Zdvihový objem" in line:
                        continue

                    row_match = _ROW_RE.match(line)
                    if row_match is None:
                        trim = line  # new trim-level heading
                        continue

                    variants.append(self._build_variant(model, trim, page.page_number, row_match))

            equipment_by_trim = parse_standard_equipment(pdf)
            for variant in variants:
                variant.equipment = equipment_by_trim.get(variant.trim, {})

        return variants

    def _build_variant(
        self, model: str, trim: str | None, source_page: int, match: re.Match[str]
    ) -> ExtractedVariant:
        engine = f"{match.group('engine').strip()} / {match.group('engine_kw')} kW"
        fuel = match.group("fuel").strip()
        price_vat = int(match.group("price_vat").replace(" ", ""))

        return ExtractedVariant(
            model=model,
            trim=trim,
            variant_name=f"{model} {trim} {engine}",
            price=price_vat,
            currency="CZK",
            source_page=source_page,
            raw_text=match.group(0),
            powertrain=_classify_powertrain(fuel),
        )

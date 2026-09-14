"""Parser for Volkswagen EV price lists (ID.3 Neo, ID.4, ID.7, ID.7
Tourer, ID. Polo) — verified against real price lists on 2026-07-19.

Same line-based format as `volkswagen.VolkswagenParser` (ICE), but the
engine description is NOT consistent across models — both the power/
battery order and the separators differ:

    ID.4 Pure 140 kW, 58 kWh E212JMA2 Automatická Zadní 792 562 Kč 959 000 Kč
    ID.7 GTX People 250 kW 4M, 86 kWh ED29PMA2 Automatická Všech kol ...
    ID.3 Neo Trend 50 kWh 125 kW E132HBA2 Automatická Zadní ...
    ID. Polo Trend 37 kWh 85 kW ES12CD* Automatická Přední ...

Instead of having the regex parse power/battery separately (and deal
with both orderings plus inconsistent text between them like "4M,"), the
whole description is taken as a single block of text anchored from the
right — the code/transmission/drivetrain/prices always have the same
shape regardless of model, so it's enough to capture THOSE and store
everything before them as the description (and also, unchanged, in
`raw_text`/`variant_name`, so it can always be traced back to the PDF)."""
from __future__ import annotations

import re
from pathlib import Path

import pdfplumber

from .base import BaseParser, ExtractedVariant
from .volkswagen import _MODEL_HEADER_RE, _TABLE_HEADER_MARKER
from .vw_equipment import parse_standard_equipment

_ROW_RE = re.compile(
    r"^(?P<description>.+?)\s+"
    r"(?P<code>\S+)\s+"
    r"(?P<transmission>Automatická|Manuální)\s+"
    r"(?P<drivetrain>Přední|Zadní|Všech kol)\s+"
    r"(?P<price_novat>[\d ]+?)\s*Kč\s+"
    r"(?P<price_vat>[\d ]+?)\s*Kč$"
)


class VolkswagenEvParser(BaseParser):
    brand = "volkswagen"
    powertrain = "EV"

    def parse(self, pdf_path: Path) -> list[ExtractedVariant]:
        """See module docstring for why the engine/battery description is
        captured as one right-anchored block rather than parsed field by
        field.

        Args:
            pdf_path: Local path to a downloaded VW EV price-list PDF.

        Returns:
            One `ExtractedVariant` per trim/battery row found, all with
            `powertrain="EV"`.
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

                trim: str | None = None
                for line in lines[1:]:
                    line = line.strip()
                    if not line:
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
        description = match.group("description").strip()
        price_vat = int(match.group("price_vat").replace(" ", ""))

        return ExtractedVariant(
            model=model,
            trim=trim,
            variant_name=description,
            price=price_vat,
            currency="CZK",
            source_page=source_page,
            raw_text=match.group(0),
            powertrain=self.powertrain,
        )

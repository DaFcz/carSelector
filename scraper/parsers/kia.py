"""Parser for Kia price lists (Niro, Ceed SW, Sportage — verified against
real PDF price lists downloaded 2026-08-13 from kia.com, effective from
2026-08-01).

Unlike Škoda (word-position table reconstruction, no PDF grid — see
skoda_ice.py) and closer to Volkswagen, `pdfplumber.extract_text()` gives
one line per row:

    1.6 T-GDI GPF 4x2 6MT 150 k / 110 kW 729 980 50 000 50 000 20 000 609 980

engine/transmission/drivetrain description, then a variable number of
price-like columns (CENÍKOVÁ CENA / SLEVA / LETNÍ BONUS / VÝKUPNÍ BONUS /
AKČNÍ CENA — which of these are present differs by model AND even by row
within the same table: e.g. on the Sportage HEV/PHEV price list, PHEV
rows skip the seasonal/trade-in bonus columns that HEV rows on the same
page have). Rather than parse every column, only the first one
(CENÍKOVÁ CENA, the standard list price — matching what Škoda/VW report
as `price`) is extracted; the later columns are a time-limited monthly
promotion (the cover page reads "Platnost ceníku od: 1. 8. 2026 -
31. 8. 2026" — a closed date RANGE that resets monthly, unlike Škoda/VW's
open-ended "Platnost od D. M. RRRR"). Because of that, `extract_release_date`
in `_pdf_layout.py` doesn't match Kia's cover text, so `release_date`
stays None for Kia documents — VariantRepository falls back to the
download date, which is an accepted gap for now rather than stretching a
shared helper to fit a third date format.

Numbers above 999 999 Kč are split by the thousands-separator space into
multiple tokens (e.g. "1", "079", "980" for 1 079 980 Kč), same as
Škoda/VW. Unlike Škoda, word x0-position isn't needed to tell where the
price ends: its own continuation groups are always exactly 3 digits,
while the column right after it (a bonus amount, e.g. "40 000") always
STARTS with a 1-2 digit token — so greedily absorbing exactly-3-digit
tokens after the first one reliably stops in the right place (see
`_leading_price`).

One Kia model can have its ICE and HEV/PHEV price lists as two entirely
separate PDF documents (Sportage) rather than two tables in one document
(Škoda) or mixed rows in one document (VW) — see
`monitors/discovery/kia.py`. Both documents share the exact row format
handled here, so this single parser class covers both; only the
discoverer needs to know about the split.

Trim levels (Comfort/Style/Premium, SPIN/TOP, BLACK EDITION/GT-Line, ...)
are their own line directly above the rows they apply to — same
convention as `volkswagen.py`.

Equipment is extracted separately from the "Hlavní prvky standardní
výbavy" bullet page (page 3, right after the price table) — see
`kia_equipment.py`'s own module docstring for the delta-by-reference
convention it follows and the availability-matrix page it deliberately
doesn't cover yet. Trims for `parse_standard_equipment` are collected
from the variants already parsed above (same two-pass "parse rows first,
then derive the trim list, then backfill `equipment`" shape as
`mazda.py`), since the bullet page's own headings are matched against
that same already-extracted trim text rather than parsed fresh."""
from __future__ import annotations

import re
from pathlib import Path

import pdfplumber

from .base import BaseParser, ExtractedVariant
from .kia_equipment import parse_standard_equipment

_ROW_RE = re.compile(
    r"^(?P<engine>.+?\s\d+\s*k\s*/\s*\d+\s*kW)\s+(?P<tail>[\d ]+)$"
)
_MARKETING_PREFIXES = ("Nový ", "Nová ", "Nové ", "Kia ")
_TABLE_HEADER_MARKER = "SPECIFIKACE"


def _extract_model_name(pdf: pdfplumber.PDF) -> str:
    """The model name is the first line of the cover page, e.g. 'Nová
    Sportage', 'Nové Niro', 'Kia Ceed SW' — the marketing prefix isn't
    part of the name used elsewhere (sources.yaml, discovery/kia.py), so
    it's stripped the same way as there."""
    cover_text = pdf.pages[0].extract_text() or ""
    lines = cover_text.strip().splitlines()
    if not lines:
        return "unknown"
    first_line = lines[0].strip()
    for prefix in _MARKETING_PREFIXES:
        if first_line.startswith(prefix):
            return first_line.removeprefix(prefix).strip()
    return first_line


def _leading_price(tail: str) -> float | None:
    """Extracts the first (CENÍKOVÁ CENA / list price) number from the
    space-separated digit tail after '... kW'. See module docstring for
    why absorbing exactly-3-digit continuations is unambiguous here."""
    tokens = tail.split()
    if not tokens or not tokens[0].isdigit():
        return None
    digits = tokens[0]
    for token in tokens[1:]:
        if len(token) == 3 and token.isdigit():
            digits += token
        else:
            break
    return float(digits)


def _classify_powertrain(engine: str) -> str:
    if "PHEV" in engine:
        return "PHEV"
    if "MHEV" in engine:
        return "MHEV"
    if "HEV" in engine:
        return "HEV"
    return "ICE"


class KiaParser(BaseParser):
    brand = "kia"
    powertrain = "ICE"  # nominal default; the actual powertrain is per-row, see _classify_powertrain

    def parse(self, pdf_path: Path) -> list[ExtractedVariant]:
        """See module docstring for Kia's row format and why only the
        list price (not the monthly promotion columns) is extracted.

        Args:
            pdf_path: Local path to a downloaded Kia price-list PDF.

        Returns:
            One `ExtractedVariant` per price row found (across all
            pages with a `_TABLE_HEADER_MARKER` table), `powertrain`
            classified per-row via `_classify_powertrain` and `equipment`
            populated from the "Hlavní prvky standardní výbavy" bullet
            page where available (see `kia_equipment.parse_standard_equipment`).
        """
        variants: list[ExtractedVariant] = []

        with pdfplumber.open(pdf_path) as pdf:
            model = _extract_model_name(pdf)

            for page in pdf.pages:
                text = page.extract_text() or ""
                if _TABLE_HEADER_MARKER not in text:
                    continue  # page without a price table (standard/optional equipment, colors, ...)

                trim: str | None = None
                for line in text.splitlines():
                    line = line.strip()
                    if not line:
                        continue

                    row_match = _ROW_RE.match(line)
                    if row_match is None:
                        # Not a price row: either a trim-level heading
                        # (e.g. "Comfort"), or the table header/footer
                        # lines ("SPECIFIKACE ...", "VÁŠ DEALER"). The
                        # latter are harmless to store here — they're
                        # always overwritten by the real trim heading
                        # before the next price row uses `trim`.
                        trim = line
                        continue

                    price = _leading_price(row_match.group("tail"))
                    if price is None:
                        continue

                    engine = row_match.group("engine")
                    variants.append(
                        ExtractedVariant(
                            model=model,
                            trim=trim,
                            variant_name=f"{model} {trim} {engine}",
                            price=price,
                            currency="CZK",
                            source_page=page.page_number,
                            raw_text=line,
                            powertrain=_classify_powertrain(engine),
                        )
                    )

            trims: list[str] = []
            for variant in variants:
                if variant.trim is not None and variant.trim not in trims:
                    trims.append(variant.trim)

            equipment_by_trim = parse_standard_equipment(pdf, trims)
            for variant in variants:
                variant.equipment = equipment_by_trim.get(variant.trim, {})

        return variants

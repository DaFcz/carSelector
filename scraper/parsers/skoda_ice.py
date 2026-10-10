"""Parser for Škoda combustion-model price lists (Fabia, Scala, Kamiq,
Octavia, Karoq, Kodiaq, Superb) — verified against real PDF price lists
for all seven models (2026-07-09, fixed 2026-07-19 after a data review
audit — see test_skoda_ice_parser_multimodel.py), see
doc/arch/webScraping/IMPLEMENTATION_PLAN.md.

EVs (Enyaq, Elroq, Epiq, Peaq) have a completely different table
structure (battery/power/range instead of fuel/transmission/drivetrain)
and are handled by the separate `skoda_ev.SkodaEvParser` — see base.py
for why they're split instead of branching inside one parser.

The price table in the PDF has no grid, so table extraction can't be
used (both PyMuPDF's find_tables and pdfplumber's extract_tables return
0 tables on it). Instead, rows are reconstructed from the positions of
individual words:

1. Words on the page are grouped into lines by the `top` coordinate.
2. The line that contains the labels "Motor" and "Pohon" (in that order,
   regardless of their x-coordinate — it differs from model to model,
   e.g. for the Fabia "Pohon" is ~100 points further right than for the
   Octavia) is the table header. The "Druh"/"Převodovka"/"Pohon" columns
   and all the trim-level columns after them are then derived from their
   POSITION on this line, never from a fixed x-coordinate. Two-word trim
   names (e.g. "Top Selection") are often split across two header lines,
   so the first word is looked up on the line immediately above the main
   header.
3. Each word in a data row is assigned to the nearest of these columns
   (engine/type/transmission/drivetrain/trim level 1..N) — the same
   position-based approach used for the header, never fixed thresholds.
4. A line where the word in the "Motor" column matches an engine pattern
   (e.g. "1,5", "2,0") sets the current engine description.
5. A line where every word in the trim-level columns is either a number
   or a dash ("–" = combination not available) is a price row — it
   produces one ExtractedVariant per column with a real price. Prices
   above 999,999 Kč are split across multiple words in the PDF (e.g. "1"
   "009" "900"), so tokens in the same column are joined together.

The price as well as the engine/fuel/transmission/drivetrain/body style
from that row are stored unchanged in `raw_text` (see ExtractedVariant),
so the result can always be verified against the exact text from the PDF.
"""

from __future__ import annotations

import re
from pathlib import Path

import pdfplumber

from ._pdf_layout import (
    column_for_x,
    extract_model_name,
    group_into_lines,
    line_text,
    looks_like_toc_legend,
    merge_same_line_trim_tokens,
)
from .base import BaseParser, ExtractedVariant
from .skoda_standard_equipment import equipment_for_trim, parse_equipment

_ENGINE_START_RE = re.compile(r"^\d,\d$")  # first token of the engine, e.g. "1,5", "2,0"
_HEADER_CONTINUATION_TOLERANCE = 40  # tolerance for joining two-line trim names

# indexes of the fixed columns in the column_x/column_labels list (see _detect_header)
_COL_MOTOR, _COL_DRUH, _COL_PREVODOVKA, _COL_POHON = range(4)
_FIRST_TRIM_COLUMN = 4


def _detect_header(lines: list[list[dict]], index: int) -> tuple[list[str], list[float]] | None:
    """If `lines[index]` is the main header line of the price table,
    returns (column_names, their_x0_coordinates) — the first 4 are always
    Motor/Druh/Převodovka/Pohon, the rest are trim levels. Otherwise None.

    The absolute x-coordinate of these labels differs between models (for
    the Fabia, "Pohon" is ~100 points further than for the Octavia), so
    it's looked up by TEXT, not position — the position is only derived
    from the found line afterwards.
    """
    line = lines[index]
    texts = [w["text"] for w in line]
    if "Motor" not in texts or "Pohon" not in texts:
        return None

    motor_i = texts.index("Motor")
    pohon_i = texts.index("Pohon")
    if pohon_i <= motor_i:
        return None

    fixed_labels = texts[motor_i : pohon_i + 1]
    if fixed_labels[:1] != ["Motor"] or "Druh" not in fixed_labels or "Převodovka" not in fixed_labels:
        return None

    trim_tokens = merge_same_line_trim_tokens(line[pohon_i + 1 :])
    if not trim_tokens:
        return None

    continuation = lines[index - 1] if index > 0 else []
    if looks_like_toc_legend(continuation):
        continuation = []
    continuation_tokens = [w for w in continuation if w["x0"] > line[pohon_i]["x0"]]

    trim_labels: list[str] = []
    trim_x: list[float] = []
    for token in trim_tokens:
        prefix = next(
            (c["text"] for c in continuation_tokens if abs(c["x0"] - token["x0"]) <= _HEADER_CONTINUATION_TOLERANCE),
            None,
        )
        trim_labels.append(f"{prefix} {token['text']}" if prefix else token["text"])
        trim_x.append(token["x0"])

    column_labels = ["Motor", "Druh", "Převodovka", "Pohon", *trim_labels]
    column_x = [line[motor_i]["x0"], None, None, line[pohon_i]["x0"], *trim_x]
    # "Druh"/"Převodovka" can occasionally be missing between Motor and
    # Pohon on another line, but for the price lists handled here they're
    # always on the main header line together with Motor/Pohon — fill in
    # their real position:
    druh_i = fixed_labels.index("Druh") + motor_i
    prevodovka_i = fixed_labels.index("Převodovka") + motor_i
    column_x[_COL_DRUH] = line[druh_i]["x0"]
    column_x[_COL_PREVODOVKA] = line[prevodovka_i]["x0"]

    return column_labels, column_x


class SkodaIceParser(BaseParser):
    brand = "skoda"
    powertrain = "ICE"

    def parse(self, pdf_path: Path) -> list[ExtractedVariant]:
        """See module docstring for the word-position table
        reconstruction this parser uses (Škoda's ICE price lists have no
        PDF grid to read cells from directly).

        Args:
            pdf_path: Local path to a downloaded Škoda ICE price-list PDF.

        Returns:
            One `ExtractedVariant` per engine/trim combination found,
            with `equipment`/`equipment_surcharge` populated from the
            standard-equipment and standalone-equipment pages where
            available (see `skoda_standard_equipment.parse_equipment`).
        """
        variants: list[ExtractedVariant] = []

        with pdfplumber.open(pdf_path) as pdf:
            model = extract_model_name(pdf)
            equipment_by_trim, equipment_prices = parse_equipment(pdf)

            for page_index, page in enumerate(pdf.pages):
                words = page.extract_words()
                if not words:
                    continue
                lines = group_into_lines(words)

                header = None
                header_at = None
                for i in range(len(lines)):
                    header = _detect_header(lines, i)
                    if header:
                        header_at = i
                        break
                if header is None:
                    continue  # page without a price table (equipment, images, ...)

                column_labels, column_x = header
                trim_labels = column_labels[_FIRST_TRIM_COLUMN:]

                body_style: str | None = None  # body-style heading (Liftback/Combi/...) above the table
                # only Octavia/Superb have this (multiple body styles);
                # other models have just one body style, so there's no
                # such line in the PDF — this used to insert the literal
                # "unknown" into variant_name, now the body style is
                # simply omitted from the name instead.
                for line in lines[:header_at]:
                    text = line_text(line).strip()
                    if text and len(line) == 1 and text.isalpha() and text[0].isupper():
                        body_style = text

                current_motor = ""
                block_lines: list[str] = []

                for line in lines[header_at + 1 :]:
                    text = line_text(line)

                    cells: dict[int, list[str]] = {}
                    for word in line:
                        column = column_for_x(word["x0"], column_x)
                        cells.setdefault(column, []).append(word["text"])

                    motor_tokens = cells.get(_COL_MOTOR)
                    if motor_tokens and _ENGINE_START_RE.match(motor_tokens[0]):
                        current_motor = " ".join(motor_tokens)
                        block_lines = [text]
                        continue

                    if text.startswith("Spotřeba:"):
                        block_lines.append(text)
                        continue

                    trim_cells = {
                        col - _FIRST_TRIM_COLUMN: tokens for col, tokens in cells.items() if col >= _FIRST_TRIM_COLUMN
                    }
                    is_price_row = bool(trim_cells) and all(
                        token == "–" or token.replace(" ", "").isdigit()
                        for tokens in trim_cells.values()
                        for token in tokens
                    )

                    if not is_price_row:
                        block_lines.append(text)
                        continue

                    block_lines.append(text)
                    raw_text = " | ".join(block_lines)

                    for column, trim_label in enumerate(trim_labels):
                        tokens = trim_cells.get(column)
                        if not tokens or tokens == ["–"]:
                            continue  # this engine × trim level combination isn't offered
                        # prices above 999,999 Kč are split across multiple words ("1" "009" "900")
                        price_text = "".join(tokens).replace(" ", "")
                        if not price_text.isdigit():
                            continue

                        name_parts = [p for p in (model, body_style, current_motor, trim_label) if p]
                        variant_name = " ".join(name_parts)
                        variants.append(
                            ExtractedVariant(
                                model=model,
                                trim=trim_label,
                                variant_name=variant_name,
                                price=float(price_text),
                                currency="CZK",
                                source_page=page_index + 1,
                                raw_text=raw_text,
                                powertrain=self.powertrain,
                                equipment=equipment_for_trim(equipment_by_trim, trim_label),
                                equipment_surcharge=equipment_prices,
                            )
                        )

                    block_lines = []

        return variants

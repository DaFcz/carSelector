"""Parser for Škoda EV price lists (Enyaq, Elroq, Epiq, Peaq) — verified
against real Enyaq and Elroq price lists (2026-07-19).

Same principle as `skoda_ice.SkodaIceParser` (positional table
reconstruction from words, no grid for table extraction), but different
columns: "Verze"/"Pohon"/"Baterie"/"Dojezd" ("Version"/"Drivetrain"/
"Battery"/"Range") instead of "Motor"/"Druh"/"Převodovka"/"Pohon", and the
data is split across TWO lines per variant instead of one:

    60 140 kW 61 kWh                              <- spec (version/power/battery)
    zadní 428-456 km 1 015 000 1 125 000 – –       <- drivetrain/range/prices per trim

Trim columns (Selection/Sportline/Laurin & Klement/RS, ...) work the same
way as for ICE — a single value per column is directly that variant's
price (not an excl./incl. VAT pair like for VW), so we share
`merge_same_line_trim_tokens`/`looks_like_toc_legend`/`column_for_x` from
`_pdf_layout.py`.

"Laurin & Klement" is assembled in TWO different ways depending on the
model — for Enyaq, "Laurin" is on the same line as "&"/"Klement"; for
Elroq, "Laurin" is on the line ABOVE the header (a two-line split like
"Exclusive Selection" in the ICE price list, for Kodiaq).
`_assemble_trim_labels` handles both cases — the generic
`merge_same_line_trim_tokens` from ICE can't, because for Elroq it would
incorrectly merge "Sportline & Klement" (the nearest token BEFORE "&" on
the same line is "Sportline", not "Laurin")."""

from __future__ import annotations

from pathlib import Path

import pdfplumber

from ._pdf_layout import column_for_x, extract_model_name, group_into_lines, line_text, looks_like_toc_legend
from .base import BaseParser, ExtractedVariant
from .skoda_standard_equipment import equipment_for_trim, parse_equipment

_HEADER_CONTINUATION_TOLERANCE = 40

_COL_VERZE, _COL_POHON, _COL_BATERIE, _COL_DOJEZD = range(4)
_FIRST_TRIM_COLUMN = 4


def _assemble_trim_labels(
    raw_tokens: list[dict], continuation: list[dict], pohon_x: float
) -> tuple[list[str], list[float]]:
    """Assembles the trim-level column names/x-positions from the raw
    tokens after "Dojezd" on the main header line. See the module
    docstring for "Laurin & Klement" — either "Laurin" is right to the
    left on the same line (`merged.pop()`), or on the line above the
    header (`continuation`, matched by x0)."""
    continuation_by_x = [c for c in continuation if c["x0"] > pohon_x]

    merged: list[dict] = []
    i = 0
    while i < len(raw_tokens):
        token = raw_tokens[i]
        if token["text"] != "&":
            merged.append(token)
            i += 1
            continue

        right = raw_tokens[i + 1]["text"] if i + 1 < len(raw_tokens) else ""
        prefix = next(
            (c["text"] for c in continuation_by_x if abs(c["x0"] - token["x0"]) <= _HEADER_CONTINUATION_TOLERANCE),
            None,
        )
        if prefix is not None:
            merged.append({"text": f"{prefix} & {right}".strip(), "x0": token["x0"]})
        elif merged:
            left = merged.pop()
            merged.append({"text": f"{left['text']} & {right}".strip(), "x0": left["x0"]})
        else:
            merged.append(token)
        i += 2

    return [m["text"] for m in merged], [m["x0"] for m in merged]


def _detect_header(lines: list[list[dict]], index: int) -> tuple[list[str], list[float], str | None] | None:
    """Like `skoda_ice._detect_header`, but for EV columns. The body style
    (SUV/Coupé) is here on the MAIN header line between "Verze" and
    "Pohon" (for Enyaq), not on a separate line above the table like for
    ICE — for models with a single body style (Elroq) there's nothing there."""
    line = lines[index]
    texts = [w["text"] for w in line]
    if "Verze" not in texts or "Pohon" not in texts or "Baterie" not in texts or "Dojezd" not in texts:
        return None

    verze_i = texts.index("Verze")
    pohon_i = texts.index("Pohon")
    baterie_i = texts.index("Baterie")
    dojezd_i = texts.index("Dojezd")
    if not (verze_i < pohon_i < baterie_i < dojezd_i):
        return None

    body_style = line_text(line[verze_i + 1 : pohon_i]).strip() or None

    continuation = lines[index - 1] if index > 0 else []
    if looks_like_toc_legend(continuation):
        continuation = []

    trim_labels, trim_x = _assemble_trim_labels(line[dojezd_i + 1 :], continuation, line[pohon_i]["x0"])
    if not trim_labels:
        return None

    column_labels = ["Verze", "Pohon", "Baterie", "Dojezd", *trim_labels]
    column_x = [line[verze_i]["x0"], line[pohon_i]["x0"], line[baterie_i]["x0"], line[dojezd_i]["x0"], *trim_x]
    return column_labels, column_x, body_style


class SkodaEvParser(BaseParser):
    brand = "skoda"
    powertrain = "EV"

    def parse(self, pdf_path: Path) -> list[ExtractedVariant]:
        """See module docstring for the word-position table
        reconstruction this parser uses (Škoda's EV price lists have no
        PDF grid to read cells from directly).

        Args:
            pdf_path: Local path to a downloaded Škoda EV price-list PDF.

        Returns:
            One `ExtractedVariant` per trim/battery/drivetrain
            combination found, all with `powertrain="EV"`, with
            `equipment`/`equipment_surcharge` filled in the same way as
            `skoda_ice` (see `skoda_standard_equipment.parse_equipment`).
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

                # Unlike ICE (where there's at most one table per page, and
                # a possible second one is on a DIFFERENT page), Enyaq has
                # both an SUV and a Coupé table on the SAME page — so the
                # header is looked up on EVERY line as we go, not just
                # once at the start of the page, so that column_x/
                # trim_labels/body_style switch over on a new "Verze ..."
                # header.
                column_x: list[float] | None = None
                trim_labels: list[str] | None = None
                body_style: str | None = None
                current_spec = ""
                block_lines: list[str] = []

                for i, line in enumerate(lines):
                    header = _detect_header(lines, i)
                    if header:
                        column_labels, column_x, body_style = header
                        trim_labels = column_labels[_FIRST_TRIM_COLUMN:]
                        current_spec = ""
                        block_lines = []
                        continue

                    if column_x is None:
                        continue  # no table found on this page yet

                    text = line_text(line)

                    if text.startswith("Spotřeba:"):
                        block_lines.append(text)
                        continue

                    cells: dict[int, list[str]] = {}
                    for word in line:
                        column = column_for_x(word["x0"], column_x)
                        cells.setdefault(column, []).append(word["text"])

                    verze_tokens = cells.get(_COL_VERZE)
                    pohon_tokens = cells.get(_COL_POHON)

                    if verze_tokens and not pohon_tokens:
                        # spec line: "60 140 kW" (version/power) + "61 kWh" (battery)
                        baterie_tokens = cells.get(_COL_BATERIE, [])
                        current_spec = " ".join([*verze_tokens, *baterie_tokens])
                        block_lines = [text]
                        continue

                    if not pohon_tokens:
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
                            continue  # this version × trim level combination isn't offered

                        price_text = "".join(tokens).replace(" ", "")
                        if not price_text.isdigit():
                            continue

                        name_parts = [p for p in (model, body_style, current_spec, trim_label) if p]
                        variants.append(
                            ExtractedVariant(
                                model=model,
                                trim=trim_label,
                                variant_name=" ".join(name_parts),
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

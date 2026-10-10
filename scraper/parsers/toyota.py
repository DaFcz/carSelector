"""Parser for Toyota price lists (Yaris, Yaris Cross, Corolla Sedan/
Hatchback/Touring Sports, C-HR, RAV4 — verified against real PDF price
lists downloaded 2026-08-13 from pdf.sites.toyota.cz, effective from
various 2026 dates per model).

Unlike Kia/VW (plain line-based text, see kia.py/volkswagen.py) and like
Škoda, the price table is a genuine grid: one column per trim level, one
row per engine, with "–" marking an engine x trim combination that isn't
offered. Word x0-position (pdfplumber) is needed to reconstruct it,
since a flattened text line like

    2.5 Hybrid (185 k) aut. převodovka e-CVT FWD benzín 1 090 000 1 240 000 – 1 340 000

is ambiguous from tokens alone: every price here is in the hundreds of
thousands, so its own thousands-groups AND the next column's leading
group are both exactly 3 digits — unlike Kia, where a short 1-2 digit
discount-column token reliably broke the tie (see kia.py).

Column assignment here uses NEAREST x0, not the interval/"last column
whose left edge is at or before x0" logic in `_pdf_layout.column_for_x`
(built for Škoda's left-aligned columns) — Toyota's price cells are
right-aligned under each trim header, so a price's leading digit group
can sit up to ~7pt to the LEFT of its column header's own x0 (see
`_nearest_column`). Toyota's columns are spaced far enough apart
(60-80pt) relative to the gap between digit groups within one number
(5-16pt) that nearest-neighbor matching is unambiguous here, even though
Škoda deliberately avoids it for its own, more tightly packed columns.

The header row's exact wording varies by body style ("SUV", "Sedan",
"5dveřový hatchback", "Touring Sports (Kombi)", ...) and isn't a fixed
marker to search for; instead the header is always the line immediately
following "Modelový rok: ... Ceník platí od ...", and its own leading
body-style word(s) are dropped by cross-referencing against where the
first data row's price cells actually start (the word right after
"benzín" — present at the end of every engine description, since
Toyota's whole CZ lineup here is hybrid/plug-in-hybrid).

Some trims are two separate header words ("GR" + "SPORT" -> "GR SPORT",
"Comfort" + "Plus" -> "Comfort Plus" on C-HR, which has both a plain
"Comfort" trim and a distinct pricier "Comfort Plus" one) — merged the
same principle as skoda_ice.py's known multi-word trim names, see
_COMPOUND_TRIMS. Trailing "*" footnote markers on trim labels (e.g.
"Style*", "Executive*") reference a paint/colour condition disclaimer,
not part of the name, and are stripped.

The cover page's model-name lines are inconsistently laid out (brand and
"Nová"/"Nový"/"Nové" prefix sometimes share a line with the model name,
sometimes not, e.g. "NOVÁ\\nTOYOTA\\nRAV4" vs "TOYOTA\\nYARIS"), so the
model name is reconstructed from every line before the fixed "MODELOVÝ
ROK ..." marker, dropping brand/marketing words — see
`_extract_model_name`.

Like Kia, `_pdf_layout.extract_release_date` doesn't match Toyota's
cover text format ("Ceník platí od D. M. RRRR", not "Platnost od"), so
`release_date` stays None here too — an accepted gap, not fixed for a
third/fourth date format (see kia.py for the same call).

No equipment extraction yet (matches Volkswagen/Kia's current scope)."""

from __future__ import annotations

from pathlib import Path

import pdfplumber

from ._pdf_layout import group_into_lines, line_text
from .base import BaseParser, ExtractedVariant

_MARKETING_WORDS = {"TOYOTA", "NOVÁ", "NOVÝ", "NOVÉ"}
_FUEL_MARKER = "benzín"
_HEADER_CUTOFF_TOLERANCE = 10  # tolerance (points) for dropping the header's leading body-style word(s)


def _normalize_word(word: str) -> str:
    """'RAV4'/'C-HR'-style branding keeps its own capitalization; every
    other word is title-cased ('YARIS' -> 'Yaris')."""
    if any(ch.isdigit() for ch in word) or ("-" in word and all(len(p) <= 3 for p in word.split("-"))):
        return word
    return word.capitalize()


def _extract_model_name(pdf: pdfplumber.PDF) -> str:
    cover_text = (pdf.pages[0].extract_text() or "").replace("‑", "-")  # non-breaking hyphen -> ascii "-"
    words: list[str] = []
    for line in cover_text.strip().splitlines():
        if line.strip().startswith("MODELOVÝ ROK"):
            break
        words.extend(w for w in line.strip().split() if w not in _MARKETING_WORDS)
    if not words:
        return "unknown"
    return " ".join(_normalize_word(w) for w in words)


_COMPOUND_TRIMS = {("GR", "SPORT"), ("Comfort", "Plus")}


def _merge_trim_tokens(tokens: list[dict]) -> list[dict]:
    merged: list[dict] = []
    i = 0
    while i < len(tokens):
        text = tokens[i]["text"].rstrip("*")
        next_text = tokens[i + 1]["text"].rstrip("*") if i + 1 < len(tokens) else None
        if next_text is not None and (text, next_text) in _COMPOUND_TRIMS:
            merged.append({"text": f"{text} {next_text}", "x0": tokens[i]["x0"]})
            i += 2
        else:
            merged.append({"text": text, "x0": tokens[i]["x0"]})
            i += 1
    return merged


def _nearest_column(x0: float, column_x: list[float]) -> int:
    return min(range(len(column_x)), key=lambda i: abs(column_x[i] - x0))


def _first_price_x0(line: list[dict]) -> float | None:
    fuel_index = next((i for i, w in enumerate(line) if w["text"] == _FUEL_MARKER), None)
    if fuel_index is None or fuel_index + 1 >= len(line):
        return None
    return line[fuel_index + 1]["x0"]


def _classify_powertrain(engine: str) -> str:
    if "Plug-in Hybrid" in engine:
        return "PHEV"
    if "Hybrid" in engine:
        return "HEV"
    return "ICE"


class ToyotaParser(BaseParser):
    brand = "toyota"
    powertrain = "HEV"  # nominal default; the actual powertrain is per-row, see _classify_powertrain

    def parse(self, pdf_path: Path) -> list[ExtractedVariant]:
        """See module docstring for Toyota's row format.

        Args:
            pdf_path: Local path to a downloaded Toyota price-list PDF.

        Returns:
            One `ExtractedVariant` per trim/engine row found,
            `powertrain` classified per-row via `_classify_powertrain`
            (Toyota's lineup here is HEV/PHEV only, never plain ICE).
        """
        variants: list[ExtractedVariant] = []

        with pdfplumber.open(pdf_path) as pdf:
            model = _extract_model_name(pdf)

            for page in pdf.pages:
                text = page.extract_text() or ""
                if "Modelový rok" not in text:
                    continue

                lines = group_into_lines(page.extract_words())
                header_at = next(
                    (i for i, line in enumerate(lines) if line_text(line).startswith("Modelový rok")),
                    None,
                )
                if header_at is None or header_at + 2 >= len(lines):
                    continue

                header_line = lines[header_at + 1]
                first_data_line = lines[header_at + 2]

                cutoff_x0 = _first_price_x0(first_data_line)
                if cutoff_x0 is None:
                    continue

                trim_tokens = _merge_trim_tokens(
                    [w for w in header_line if w["x0"] >= cutoff_x0 - _HEADER_CUTOFF_TOLERANCE]
                )
                if not trim_tokens:
                    continue
                trim_labels = [t["text"] for t in trim_tokens]
                column_x = [t["x0"] for t in trim_tokens]

                for line in lines[header_at + 2 :]:
                    fuel_index = next((i for i, w in enumerate(line) if w["text"] == _FUEL_MARKER), None)
                    if fuel_index is None or not line[0]["text"][:1].isdigit():
                        continue  # not a price row (marketing text, footnotes, ...)

                    engine = line_text(line[: fuel_index + 1])
                    price_words = line[fuel_index + 1 :]

                    cells: dict[int, list[str]] = {}
                    for word in price_words:
                        column = _nearest_column(word["x0"], column_x)
                        cells.setdefault(column, []).append(word["text"])

                    for column, trim_label in enumerate(trim_labels):
                        tokens = cells.get(column)
                        if not tokens or tokens == ["–"]:
                            continue  # this engine x trim combination isn't offered
                        price_text = "".join(tokens).replace(" ", "")
                        if not price_text.isdigit():
                            continue

                        variants.append(
                            ExtractedVariant(
                                model=model,
                                trim=trim_label,
                                variant_name=f"{model} {trim_label} {engine}",
                                price=float(price_text),
                                currency="CZK",
                                source_page=page.page_number,
                                raw_text=f"{engine} | {line_text(line)}",
                                powertrain=_classify_powertrain(engine),
                            )
                        )

        return variants

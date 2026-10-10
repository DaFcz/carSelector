"""Helper functions for reconstructing PDF tables from word positions
(pdfplumber), shared between the Škoda ICE and EV parsers (and
potentially other OEMs whose price lists have a similarly non-tabular
structure).
"""

from __future__ import annotations

import re
from datetime import date

import pdfplumber

LINE_TOLERANCE = 4  # tolerance (in points) for grouping words into a single line
# "(?:ceníku )?": MG's own cover page reads "Platnost ceníku od D. M. RRRR."
# rather than every other brand's plain "Platnost od ..." - a harmless
# widening since it only adds an alternative, not narrows the existing match.
_RELEASE_DATE_RE = re.compile(r"Platnost (?:ceníku )?od (\d{1,2})\.\s*(\d{1,2})\.\s*(\d{4})")


def group_into_lines(words: list[dict]) -> list[list[dict]]:
    """Groups words into lines by the `top` coordinate and sorts them by x0."""
    lines: list[list[dict]] = []
    for word in sorted(words, key=lambda w: (w["top"], w["x0"])):
        if lines and abs(lines[-1][0]["top"] - word["top"]) <= LINE_TOLERANCE:
            lines[-1].append(word)
        else:
            lines.append([word])
    for line in lines:
        line.sort(key=lambda w: w["x0"])
    return lines


def line_text(line: list[dict]) -> str:
    return " ".join(w["text"] for w in line)


def extract_model_name(pdf: pdfplumber.PDF) -> str:
    """The model name is on the cover page as a line reading 'Škoda <Model>'."""
    cover_text = pdf.pages[0].extract_text() or ""
    for line in cover_text.strip().splitlines():
        if line.strip().startswith("Škoda "):
            return line.strip().removeprefix("Škoda ").strip()
    return "unknown"


def column_for_x(x0: float, column_x: list[float], *, tolerance: float = 2.0) -> int:
    """Returns the index of the last column whose left edge (`column_x[i]`)
    lies at or before `x0` (an interval check, not "nearest column").

    Prices above 999,999 Kč are split across multiple words in the PDF
    (e.g. "469" and "900" for "469 900"). The second word tends to sit
    ~35-40 points further right than the first, which is the same order
    of magnitude as the gap between two adjacent columns for models with
    more tightly packed trim levels (for Fabia/Kamiq/Karoq, "Top" and the
    second "Selection" column are only ~42 points apart) — comparing
    "nearest column" then mistakenly assigns the second word to the
    neighboring column on the right. The left edge of a column is a
    reliable signal, though, because the price list template left-aligns
    columns: a token belongs to the last column that hasn't started to
    its right yet.
    """
    index = 0
    for i, x in enumerate(column_x):
        if x is not None and x0 >= x - tolerance:
            index = i
    return index


_LIST_MARKER_RE = re.compile(r"^\d+\.$")  # "1.", "2." ... numbered items in the "Nový vůz krok za krokem" legend


def looks_like_toc_legend(line: list[dict]) -> bool:
    """The line "Nový vůz krok za krokem 1. Motorizace 2. Standardní výbava
    ..." ("New car step by step 1. Engines 2. Standard equipment ...") is a
    fixed legend that repeats above every price/equipment table for models
    without their own body-style line (Fabia/Kamiq/Karoq/Scala — unlike
    Octavia/Superb, where there's also a "Liftback"/"Combi"/"Verze SUV"
    line between the legend and the header). It's recognized by ≥2
    numbered items ("1.", "2.", ...) and must NOT be treated as the
    continuation of a two-word trim name (otherwise you get "5. Selection",
    "Pakety Top", "prvky Carlo", etc.). Shared between the Škoda ICE and EV
    parsers (both have the same legend above the table)."""
    return sum(1 for w in line if _LIST_MARKER_RE.match(w["text"])) >= 2


def merge_same_line_trim_tokens(tokens: list[dict]) -> list[dict]:
    """Merges tokens on the SAME header line that together form one
    (real, official) trim name, but where the gap between them isn't
    reliably smaller than the gap between adjacent columns (so it can't be
    solved with a generic distance threshold — verified against
    `extract_text()` on the PDF):

    - "Laurin" "&" "Klement" -> "Laurin & Klement" (Superb, Enyaq) — "&"
      is never a standalone trim name.
    - "Top" "Selection" -> "Top Selection" (Fabia/Kamiq/Karoq/Scala) — the
      same trim as on the Octavia (there it comes from a two-line header),
      but here "Top" and "Selection" are on the same line, only 42.9
      points apart — a SMALLER gap than "Monte"/"Carlo" (70.5 points)
      further along the same header, so generic distance-based clustering
      wouldn't be able to tell the two cases apart.
    - "Monte" "Carlo" -> "Monte Carlo" (a Fabia/Kamiq/Scala trim).

    Shared between the Škoda ICE and EV parsers (same header pattern)."""
    merged: list[dict] = []
    i = 0
    while i < len(tokens):
        if i + 2 < len(tokens) and tokens[i + 1]["text"] == "&":
            merged.append({"text": f"{tokens[i]['text']} & {tokens[i + 2]['text']}", "x0": tokens[i]["x0"]})
            i += 3
        elif i + 1 < len(tokens) and tokens[i]["text"] == "Top" and tokens[i + 1]["text"] == "Selection":
            merged.append({"text": "Top Selection", "x0": tokens[i]["x0"]})
            i += 2
        elif i + 1 < len(tokens) and tokens[i]["text"] == "Monte" and tokens[i + 1]["text"] == "Carlo":
            merged.append({"text": "Monte Carlo", "x0": tokens[i]["x0"]})
            i += 2
        else:
            merged.append(tokens[i])
            i += 1
    return merged


_ROTATED_COLUMN_TOLERANCE = 3  # tolerance (in points) for grouping rotated characters into a column


def group_rotated_chars_into_columns(chars: list[dict]) -> list[dict]:
    """Assembles readable labels from characters rotated 90° (`upright=False`,
    typically column headers of equipment matrices — "Pakety"/"Samostatné
    prvky výbavy"). pdfplumber returns these characters in the order they
    appear in the PDF stream (not in reading order), so `extract_text()`
    turns them into a scrambled string (e.g. "ecnessE" instead of "Essence").

    Characters with the same (rounded) `x0` belong to the same column;
    within a column they're read top to bottom in order of DECREASING
    `top` — verified on a real PDF: "E" top=246.2, "s" top=238.9, ... "e"
    top=198.4 -> "Essence".

    Returns a list of `{"text": ..., "x0": ...}` left to right (the same
    shape as words from `page.extract_words()`, so it can be used with the
    same column-assembly logic as in `skoda_ice._detect_header`).
    """
    rotated = [c for c in chars if not c.get("upright", True)]

    columns: list[list[dict]] = []
    for char in sorted(rotated, key=lambda c: (c["x0"], -c["top"])):
        if columns and abs(columns[-1][0]["x0"] - char["x0"]) <= _ROTATED_COLUMN_TOLERANCE:
            columns[-1].append(char)
        else:
            columns.append([char])

    labels: list[dict] = []
    for column in columns:
        column.sort(key=lambda c: -c["top"])
        labels.append({"text": "".join(c["text"] for c in column), "x0": column[0]["x0"]})
    return labels


def extract_release_date(pdf: pdfplumber.PDF) -> date | None:
    """The price list's effective date is on the cover page as 'Platnost od D. M. RRRR' ("Valid from D. M. YYYY")."""
    cover_text = pdf.pages[0].extract_text() or ""
    match = _RELEASE_DATE_RE.search(cover_text)
    if not match:
        return None
    day, month, year = (int(part) for part in match.groups())
    return date(year, month, day)

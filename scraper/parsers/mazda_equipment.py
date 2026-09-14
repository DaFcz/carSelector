"""Extracts per-trim standard equipment from Mazda's own VÝBAVA pages
(verified against all three fixtures: mazda_cx-5_cenik.pdf, mazda_cx-30
_cenik.pdf, mazda3_cenik.pdf). One page per category (EXTERIÉR/INTERIÉR/
BEZPEČNOST/POHODLÍ/AUDIO A INFOZÁBAVA - not every model has all five), each
a checkbox matrix: one column per trim, a mark per cell - standard/
unavailable/optional-within-a-package (no per-item price given anywhere in
this document, so - same "no CHECK-constraint-satisfying price, don't
fabricate one" stance as `dacia_equipment.py` - the optional-in-package
mark is read but never turned into an `OPTIONAL` assignment, only the
standard mark becomes `equipment[name] = "STANDARD"`).

**The three marks are NOT the same characters across the three fixtures**
(verified): CX-5's PDF happens to have them embedded as the plain letters
"l"/"m" for standard/optional, but CX-30's uses PDF CIDs with no
ToUnicode mapping - pdfplumber renders these as the literal text
"(cid:122)"/"(cid:129)" - and Mazda3's uses Private-Use-Area icon-font
glyphs instead. Hardcoding any one of these would silently return zero
items on the other two fixtures (the actual bug this module went through
before landing on the approach below - the CID/PUA rows never match a
literal "l"/"m" check). Every one of these pages carries its own legend
line spelling out what its own marks mean ("<mark> = Standardní výbava,
<mark> = Nedostupné, <mark> = Volitelné v rámci paket...") -
`_discover_marks` parses that line PER PAGE instead of assuming a fixed
alphabet, so whichever glyphs a given fixture happens to use are read
from its own legend rather than guessed.

A few cells also carry a footnote reference glued directly onto the mark
with no space (e.g. an optional-mark glyph immediately followed by
"(2)") - `_strip_footnote` drops a trailing "(<digits>)" before comparing
a token against the discovered marks, so a footnoted cell is still
recognized as that mark.

The "unavailable" mark itself has a second, independent inconsistency:
CX-5's own legend line spells it with an en dash (U+2013), but every
actual table cell in that same document uses a plain hyphen-minus
(U+002D) instead - verified via `ord()` on both. `_normalize_dash`
collapses every dash-like character to one canonical form before any
mark comparison runs, so the legend and the cells agree regardless of
which the source PDF actually used at each spot.

Unlike `dacia_equipment.py`/`skoda_equipment.py`, trim names for a page
aren't parsed fresh from that page's own header text - they're looked up
from `MazdaParser`'s own already-extracted `ExtractedVariant.trim` values
for the matching model (passed in as `trims_by_model`), since the header
line's own whitespace-joined trim names can't be split back apart
reliably: Mazda3's Hatchback table has a genuine two-word trim, "HOMURA
PLUS", printed with an ordinary single space next to "HOMURA" and "NAGISA"
("...HOMURA HOMURA PLUS NAGISA") - indistinguishable from 3 one-word trims
by a plain `.split()`. Matching each page's own item rows (which DO have a
reliable, fixed column count - the number of trims on that page) against
the already-known trim list for that model sidesteps needing to parse the
header at all.

A page's own model/body-style is read from its "VÝBAVA"/"VÝBAVA HATCHBACK"/
"VÝBAVA SEDAN" title line (the second line of `extract_text()` output) -
same `_BODY_STYLE_MARKERS`-equivalent split as `mazda.py`'s own price-page
handling, so a Mazda3 Hatchback row is matched against the Hatchback-only
trim list (7 trims) and a Sedan row against the Sedan-only list (4 trims,
no Homura/Homura Plus/Nagisa - those trims aren't sold as a Sedan).

One further wrinkle, seen only on CX-5/CX-30's BEZPEČNOST page: a few
multi-clause items (e.g. "Pokročilý protikolizní systém (přední a zadní)")
wrap across several physical lines of "- <sub-feature>" bullets, with the
row's own mark line landing on some line IN THE MIDDLE of that wrapped
block rather than at its end - apparently wherever the PDF renderer's row-
height midpoint happened to fall, not tied to any specific sub-bullet.
`_parse_marks_table` treats a bare marks-only line (no name text on it at
all) as informational only (remembers it as `pending_marks`, doesn't end
the item) and instead ends an item only when a line that does NOT start
with "-" appears while something is already buffered (that's the next
item's own name starting, with or without marks trailing on that same
line) - `pending_marks` from wherever the marks line actually landed is
applied to whatever text was buffered up to that point.
"""
from __future__ import annotations

import re

import pdfplumber

_FOOTNOTE_RE = re.compile(r"\(\d+\)$")
_LEGEND_RE = re.compile(
    r"(?P<standard>\S+)\s*=\s*Standardn\S*\s+v\S*bava,\s*"
    r"(?P<unavailable>\S+)\s*=\s*Nedostupn\S*,\s*"
    r"(?P<optional>\S+)\s*=\s*Voliteln\S*\s+v\s+r\S*mci\s+paket",
    re.IGNORECASE,
)
_DASH_CHARS = "-‐‑‒–—―"


def _normalize_dash(token: str) -> str:
    """Args:
        token: One mark token (already footnote-stripped).

    Returns:
        `"-"` if `token` is any dash-like character (see module
        docstring), else `token` unchanged.
    """
    return "-" if token in _DASH_CHARS else token


def _normalize_mark(token: str) -> str:
    """Args:
        token: One raw mark token straight off a row/legend line.

    Returns:
        `token` with its footnote reference stripped and any dash variant
        collapsed to a single canonical form - the form every mark
        comparison in this module runs against.
    """
    return _normalize_dash(_FOOTNOTE_RE.sub("", token))


def _discover_marks(lines: list[str]) -> tuple[str, str, str] | None:
    """Args:
        lines: One equipment page's text lines.

    Returns:
        `(standard_mark, unavailable_mark, optional_mark)`, normalized via
        `_normalize_mark` (see module docstring for why these vary by
        fixture), or `None` if no legend line was found.
    """
    for line in lines:
        match = _LEGEND_RE.search(line)
        if match:
            return (
                _normalize_mark(match.group("standard")),
                _normalize_mark(match.group("unavailable")),
                _normalize_mark(match.group("optional")),
            )
    return None


def _split_trailing_marks(
    tokens: list[str], column_count: int, marks_vocab: tuple[str, str, str]
) -> tuple[list[str], list[str] | None]:
    """Args:
        tokens: A line's whitespace-split tokens.
        column_count: Number of trim columns on this page (len(trims)).
        marks_vocab: This page's own normalized `(standard, unavailable,
            optional)` mark strings (see `_discover_marks`).

    Returns:
        `(name_tokens, marks)` - `marks` is the last `column_count` raw
        tokens if every one of them normalizes (see `_normalize_mark`) to
        something in `marks_vocab`, else `None` (the whole line is
        `name_tokens`, unchanged).
    """
    if len(tokens) >= column_count:
        candidate = tokens[-column_count:]
        if all(_normalize_mark(t) in marks_vocab for t in candidate):
            return tokens[:-column_count], candidate
    return tokens, None


def _parse_marks_table(
    lines: list[str], trims: list[str], marks_vocab: tuple[str, str, str]
) -> dict[str, dict[str, str]]:
    """Args:
        lines: One equipment page's text lines, starting after its own
            title/trim-header/category lines (item rows through the
            trailing legend line, which is also skipped here).
        trims: This page's trim names in column order (see module
            docstring for why these come from the price table, not this
            page's own header text).
        marks_vocab: This page's own normalized `(standard, unavailable,
            optional)` mark strings (see `_discover_marks`).

    Returns:
        `{trim: {item_name: "STANDARD"}}` - only cells matching this
        page's own standard mark; unavailable/optional cells are read (to
        correctly delimit rows) but never stored (see module docstring).
    """
    standard_mark = marks_vocab[0]
    column_count = len(trims)
    result: dict[str, dict[str, str]] = {trim: {} for trim in trims}
    buffer: list[str] = []
    pending_marks: list[str] | None = None

    def flush() -> None:
        nonlocal buffer, pending_marks
        name = " ".join(buffer).strip()
        if name and pending_marks:
            for trim, mark in zip(trims, pending_marks):
                if _normalize_mark(mark) == standard_mark:
                    result[trim][name] = "STANDARD"
        buffer = []
        pending_marks = None

    for raw_line in lines:
        line = raw_line.strip()
        if not line or _LEGEND_RE.search(line):
            continue

        name_tokens, marks = _split_trailing_marks(line.split(), column_count, marks_vocab)
        name_fragment = " ".join(name_tokens).strip()

        if not name_fragment:
            if marks:  # bare marks line mid-item, see module docstring
                pending_marks = marks
            continue

        if not name_fragment.startswith("-") and buffer:
            flush()

        buffer.append(name_fragment)
        if marks:
            pending_marks = marks

    flush()
    return result


def parse_equipment(pdf: pdfplumber.PDF, trims_by_model: dict[str, list[str]]) -> dict[str, dict[str, dict[str, str]]]:
    """Args:
        pdf: The opened Mazda price-list PDF.
        trims_by_model: Every model this document covers, mapped to its
            own trim names in the exact casing `MazdaParser` already
            produces for `ExtractedVariant.trim` (e.g. `{"CX-5":
            ["Prime-Line", "Centre-Line", ...], "3": [...], "3 Sedan":
            [...]}`) - see module docstring for why trims are looked up
            this way instead of parsed from each equipment page's own
            header.

    Returns:
        `{model: {trim: {item_name: "STANDARD"}}}`, merged across every
        VÝBAVA page found (one per category) - `{}` for a model with no
        matching page or no legend line to determine its marks from.
    """
    result: dict[str, dict[str, dict[str, str]]] = {}

    for page in pdf.pages:
        text = page.extract_text() or ""
        lines = text.splitlines()
        if len(lines) < 4 or not lines[1].strip().upper().startswith("VÝBAVA"):
            continue

        title = lines[1].strip().upper()
        # A page is either the Sedan-only table (Mazda3) or the "everything
        # else" table (bare "VÝBAVA" for CX-5/CX-30, "VÝBAVA HATCHBACK" for
        # Mazda3) - each PDF only ever covers one base model, so this alone
        # picks the right key out of trims_by_model without needing to
        # parse a model name off this page at all.
        wants_sedan = "SEDAN" in title
        model = next((m for m in trims_by_model if m.endswith(" Sedan") == wants_sedan), None)
        if model is None:
            continue

        marks_vocab = _discover_marks(lines)
        if marks_vocab is None:
            continue

        trims = trims_by_model[model]
        page_equipment = _parse_marks_table(lines[4:], trims, marks_vocab)

        model_result = result.setdefault(model, {trim: {} for trim in trims})
        for trim, items in page_equipment.items():
            model_result.setdefault(trim, {}).update(items)

    return result

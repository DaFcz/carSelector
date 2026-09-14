"""Extracts standard equipment from Volkswagen's own "Sériová Výbava"
pages (shared by both `volkswagen.VolkswagenParser` (ICE/MHEV/PHEV) and
`volkswagen_ev.VolkswagenEvParser` (EV) - verified against
vw_golf_cenik.pdf, vw_id3neo_cenik.pdf, vw_id4_cenik.pdf; the same page
layout and "Navíc oproti výbavě <trim>" convention appears in all three).

Each trim gets 1+ full pages titled "<model> Sériová Výbava <n>", body
"<Trim>" (the base trim - Golf/Trend/Pure - lists its OWN full equipment)
or "<Trim> Navíc oproti výbavě <OtherTrim>" (every higher trim lists only
what it ADDS on top of a named lower trim - not necessarily the
immediately preceding one: verified on vw_golf_cenik.pdf, where both
"Style" and "R-Line" are each "Navíc oproti výbavě Life", not Style/R-Line
building on each other, so `_resolve_trim_equipment` looks the referenced
trim up by name in whatever's already been accumulated for it rather than
assuming a linear ladder).

Item names are read from BOLD text only (`page.chars` filtered to a
"...Bold" font whose name contains "VWText" - NOT "VWHead", the larger/
bolder font used for the page's own category headings like "Vnitřní
výbava"/"Asistenční systémy a funkčnost", which this module has no need to
read at all since the API only wants standard/optional, never a category).
Each page lays items out as a 4-column card grid (verified: bold word
clusters land at x0 ≈ 20/224/427/630 on every page, evenly spaced) with a
plain (non-bold) description paragraph under each title - the description
is discarded, not stitched onto the name, since the title alone is already
a complete, real equipment name and reconstructing which description line
belongs to which of the 4 side-by-side columns would need the same kind of
column-boundary inference this module deliberately avoids by only reading
bold text: bold titles at the same visual row are naturally separated by a
much larger horizontal gap (>15pt, a whole column width) than the words
within one title (a few pt), so grouping same-row bold words by that one
gap threshold - `_cluster_items` - reconstructs every column's own titles
correctly without ever needing to know a column's own x-range up front.

VW's price lists also carry a second, much larger equipment section per
model - "Příplatková výbava" (optional, priced, per-trim availability read
off a Škoda-style rotated-header matrix with icon-font marks, e.g.
vw_golf_cenik.pdf pages 10-19) - not covered by this module. That page
shape is a materially different, harder parsing problem (rotated headers,
in-cell manufacturer codes, multi-line wrapped names, per-cell prices) on
top of what was needed just to unblock standard equipment being entirely
absent; left as a known gap rather than a rushed, unverified attempt."""
from __future__ import annotations

import re

import pdfplumber

_PAGE_TITLE_RE = re.compile(r"Sériová Výbava \d+$")
_DELTA_MARKER = " Navíc oproti výbavě "
_COLUMN_GAP = 15.0  # pt; item titles in the same card are a few pt apart, columns are 200+pt apart
_ROW_GAP = 2.0  # pt; chars/words of one title line land within ~1pt of each other in `top`


def _is_equipment_page(first_line: str) -> bool:
    """Args:
        first_line: A page's own first `extract_text()` line.

    Returns:
        Whether this page is one of the "Sériová Výbava" pages this module
        reads (as opposed to a price, "Příplatková výbava", or "Barvy"
        page - see module docstring for why the latter isn't covered).
    """
    return bool(_PAGE_TITLE_RE.search(first_line))


def _parse_trim_header(line: str) -> tuple[str, str | None]:
    """Args:
        line: An equipment page's second `extract_text()` line, e.g.
            `"Golf"` or `"Life Navíc oproti výbavě Golf"`.

    Returns:
        `(trim, referenced_trim)` - `referenced_trim` is `None` for a base
        trim's own page (nothing to inherit from).
    """
    if _DELTA_MARKER in line:
        trim, referenced = line.split(_DELTA_MARKER, 1)
        return trim.strip(), referenced.strip()
    return line.strip(), None


def _words_from_chars(chars: list[dict]) -> list[dict]:
    """Args:
        chars: `page.chars`, already filtered to the bold item-title font.

    Returns:
        Words reconstructed from `chars` - characters on (approximately)
        the same `top` within a small `x0` gap join into one word.
    """
    chars = sorted(chars, key=lambda c: (round(c["top"], 1), c["x0"]))
    words: list[list[dict]] = []
    for char in chars:
        if words and abs(words[-1][-1]["top"] - char["top"]) < 0.5 and char["x0"] - words[-1][-1]["x1"] <= 2.0:
            words[-1].append(char)
        else:
            words.append([char])
    return [
        {"text": "".join(c["text"] for c in word), "x0": word[0]["x0"], "top": word[0]["top"]} for word in words
    ]


def _cluster_items(words: list[dict]) -> list[str]:
    """Args:
        words: Bold words from one page, in any order (see
            `_words_from_chars`).

    Returns:
        One string per item title - words grouped into the same visual row
        (within `_ROW_GAP` of each other), then split into column clusters
        wherever the gap to the previous word's `x1` exceeds
        `_COLUMN_GAP` (see module docstring for why this needs no explicit
        knowledge of the page's own column x-ranges).
    """
    words = sorted(words, key=lambda w: (w["top"], w["x0"]))
    rows: list[list[dict]] = []
    for word in words:
        if rows and word["top"] - rows[-1][-1]["top"] <= _ROW_GAP:
            rows[-1].append(word)
        else:
            rows.append([word])

    items: list[str] = []
    for row in rows:
        row = sorted(row, key=lambda w: w["x0"])
        clusters: list[list[dict]] = [[row[0]]]
        for word in row[1:]:
            prev = clusters[-1][-1]
            if word["x0"] - (prev["x0"] + len(prev["text"]) * 4.5) > _COLUMN_GAP:
                clusters.append([word])
            else:
                clusters[-1].append(word)
        for cluster in clusters:
            items.append(" ".join(w["text"] for w in cluster).strip())

    return [item for item in items if item]


def _page_items(page: pdfplumber.page.Page) -> list[str]:
    """Args:
        page: One "Sériová Výbava" page.

    Returns:
        Every item title found on `page` (see `_cluster_items`).
    """
    bold_chars = [c for c in page.chars if "VWText-Bold" in c.get("fontname", "") and 7.0 <= c["size"] <= 9.0]
    return _cluster_items(_words_from_chars(bold_chars))


def parse_standard_equipment(pdf: pdfplumber.PDF) -> dict[str, dict[str, str]]:
    """Args:
        pdf: The opened VW price-list PDF.

    Returns:
        `{trim: {item_name: "STANDARD"}}`, each higher trim's dict already
        including everything a referenced lower trim has (deltas folded
        in, see module docstring) - `{}` if no "Sériová Výbava" page was
        found.
    """
    trim_equipment: dict[str, dict[str, str]] = {}
    current_trim: str | None = None

    for page in pdf.pages:
        text = page.extract_text() or ""
        lines = text.splitlines()
        if len(lines) < 2 or not _is_equipment_page(lines[0].strip()):
            continue

        trim, referenced_trim = _parse_trim_header(lines[1].strip())
        if trim != current_trim:
            current_trim = trim
            base = dict(trim_equipment[referenced_trim]) if referenced_trim in trim_equipment else {}
            trim_equipment[current_trim] = base

        for item in _page_items(page):
            trim_equipment[current_trim][item] = "STANDARD"

    return trim_equipment

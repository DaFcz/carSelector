"""Extracts standard equipment from CUPRA's own "SÉRIOVÁ VÝBAVA" pages
(verified against all six fixtures: cupra_born_cenik.pdf, cupra_formentor
_cenik.pdf, cupra_leon_cenik.pdf, cupra_leon_sportstourer_cenik.pdf,
cupra_raval_cenik.pdf, cupra_terramar_cenik.pdf). Every item here is
`STANDARD` - like `dacia_equipment.py`, CUPRA discloses no per-item price
on this page (paid extras live on a separate "VÝBAVA NA PŘÁNÍ" page, not
handled by this module - see below), so `ExtractedVariant.equipment_surcharge`
is never populated here.

Unlike Dacia's flat sequential bullet list, CUPRA lays each page out as a
2-4 column newspaper grid (verified via `page.extract_words()` x0/top
coordinates, not just `extract_text()` - the latter interleaves same-y
words from unrelated columns into one scrambled line: Born's own page 3
has col-1's "Exteriér" heading and col-2's "Bezpečnost a asistenční
systémy" heading sharing the exact same `top`, so a naive whole-page
`group_into_lines` would merge them into nonsense). Words are first
bucketed into columns by `x0` (`_cluster_columns` - a 60pt gap between two
columns' `x0` values is far bigger than the few points of jitter between
a category heading's indent and its own column's item indent), and only
THEN grouped into lines per column - so a heading and an item that merely
share a `y` position in different columns never mix.

Each column is its own top-to-bottom read: a trim name (or "TRIM /navíc
oproti výbavě OTHER" - "TRIM, in addition to OTHER's equipment") at font
size 10 starts a trim section that carries on through any following
category headings ("Exteriér", "Bezpečnost a asistenční systémy", ... -
the SAME font size as an item, 8pt, but weight `Montserrat-SemiBold`
where an item is `Montserrat-Regular`/`-Thin`, verified via
`extract_words(extra_attrs=["fontname", "size"])` - a category heading is
otherwise textually indistinguishable from an item, e.g. Leon's own
"Interiér DYNAMIC" is a plain item, not the "Interiér" category heading,
and only the font weight tells them apart) until either a new trim
heading appears or the column ends. A trim section ends up spanning
MULTIPLE columns/pages this way without ever re-declaring itself (Leon's
own page 4: column 3 opens directly with "Elektronicky řízený ..." items,
no heading of its own - still `VZ`, carried over from column 2's "VZ
/navíc oproti výbavě CUPRA" heading, until a fresh "VZ Extreme /navíc
oproti výbavě CUPRA" heading appears further down that same column) - so
trim state is carried across column (and page) boundaries and only ever
changed by an actual heading line, never reset by a mere column/page
break.

A CUPRA heading or item can itself wrap onto a second physical line
(Raval's own page 4: "ENDURANCE /navíc oproti výbavě" then, 12pt below,
just "RAVAL" - one heading split in two) - detected via the same
`top`-gap signature `mazda_equipment.py` already relies on for its own
wrapped sub-bullets: a normal gap between two distinct lines in the same
column is ~19-20pt here, a wrapped continuation's gap is about half that
(~9-12pt, verified across Born/Formentor/Raval). `_group_units` buffers
consecutive same-style lines under that gap threshold into one logical
heading/item before classifying it, so a wrapped "ENDURANCE /navíc
oproti výbavě RAVAL" heading (or a wrapped item like "Elektronicky řízený
samosvorný diferenciál přední nápravy (XDS)") is read as a whole rather
than as two unrelated fragments.

A "TRIM /navíc oproti výbavě OTHER" heading always names its own base
trim explicitly (never "whatever came right before", unlike Dacia's
implicit chaining) - `_apply_heading` looks `OTHER` up directly in the
`results` dict built so far and copies its accumulated items forward,
which only works because CUPRA's own documents always introduce a base
trim's full section before any of its deltas (true in all six fixtures).
A referenced trim that hasn't been seen yet (shouldn't happen in
practice) simply contributes no items rather than raising - a milder
version of the same "don't fabricate, degrade gracefully" stance as
`dacia_equipment.py`'s own handling of an unresolved base trim.

Only pages whose OWN title line (not the "Sériová výbava / Výbava na
přání" breadcrumb that ALSO appears, verbatim, on every "VÝBAVA NA
PŘÁNÍ" page) reads "... SÉRIOVÁ VÝBAVA <n>" are read here. The paid
"VÝBAVA NA PŘÁNÍ" pages (packages, individually-priced options, colors)
are a substantially harder shape to parse - among other things, several
of their own column headers are mirrored top-to-bottom in the PDF stream
(`extract_text()` renders Born's own "REBORN" column, for instance, as
the literal reversed string "NROBER") - and aren't handled by this
module, the same scope line `skoda_equipment.py` draws around its own
"Pakety" pages and `dacia_equipment.py` draws around packages generally.

A handful of trim names that show up on these equipment pages (CUPRA's
own "Tribe" sub-tables, and Formentor's own "VZ5" one) don't correspond
to any trim actually sold in that same document's own price table
(verified against each fixture's own page 2) - harmless here, since
nothing ever looks those keys up; just a sign CUPRA reuses one shared
page template across markets/editions that don't all sell the same trim
mix.
"""
from __future__ import annotations

import re

import pdfplumber

from ._pdf_layout import group_into_lines, line_text

_TITLE_MARKER = "sériová výbava"
_TITLE_TOP_MAX = 50.0  # points; excludes the page's own big title line from column/line detection
_HEADING_SIZE_MIN = 9.0  # trim headings are 10pt, category headings 8pt (see module docstring)
_COLUMN_GAP = 60.0  # points; smaller than the ~200pt gap between real columns, bigger than in-column indent jitter
_UNIT_GAP_MAX = 14.0  # points; below this, a line is a wrapped continuation of the previous one (see module docstring)

_DELTA_RE = re.compile(r"^(?P<trim>.+?)\s+/navíc\s+oproti\s+výbavě\s+(?P<base>.+)$")


def _is_heading(line: list[dict]) -> bool:
    return all("SemiBold" in w["fontname"] for w in line)


def _cluster_columns(xs: list[float]) -> list[float]:
    """Args:
        xs: Every content word's `x0` on one page (title excluded).

    Returns:
        One anchor per column, left to right - the leftmost `x0` of each
        cluster of values less than `_COLUMN_GAP` points apart (see
        module docstring for why that threshold safely separates real
        columns from a category heading's own small indent).
    """
    anchors: list[float] = []
    for x in sorted(xs):
        if not anchors or x - anchors[-1] > _COLUMN_GAP:
            anchors.append(x)
    return anchors


def _nearest_column(x0: float, anchors: list[float]) -> int:
    return min(range(len(anchors)), key=lambda i: abs(anchors[i] - x0))


def _group_units(lines: list[list[dict]]) -> list[tuple[str, bool, float]]:
    """Args:
        lines: One column's lines, top to bottom (already grouped via
            `group_into_lines`).

    Returns:
        `(text, is_heading, size)` per logical unit - consecutive lines of
        the same style (heading/item, same font size) closer together
        than `_UNIT_GAP_MAX` are merged into one unit first, so a wrapped
        heading or item is read as a whole (see module docstring).
    """
    units: list[tuple[str, bool, float]] = []
    buffer: list[str] = []
    buffer_style: tuple[bool, float] | None = None
    prev_top: float | None = None

    def flush() -> None:
        if buffer and buffer_style is not None:
            units.append((" ".join(buffer).strip(), buffer_style[0], buffer_style[1]))

    for line in lines:
        style = (_is_heading(line), line[0]["size"])
        top = line[0]["top"]
        if buffer and style == buffer_style and prev_top is not None and (top - prev_top) < _UNIT_GAP_MAX:
            buffer.append(line_text(line))
        else:
            flush()
            buffer = [line_text(line)]
            buffer_style = style
        prev_top = top

    flush()
    return units


def _apply_heading(text: str, results: dict[str, dict[str, str]]) -> str:
    """Args:
        text: A trim-heading unit's text (10pt, SemiBold) - either a bare
            trim name or a "TRIM /navíc oproti výbavě OTHER" delta.
        results: Equipment accumulated so far, keyed by trim - mutated to
            ensure the returned trim has an (at minimum empty) entry.

    Returns:
        The trim name now in effect (see module docstring for how a
        delta heading's base is resolved).
    """
    match = _DELTA_RE.match(text)
    if match is None:
        trim = text.strip()
        results.setdefault(trim, {})
        return trim

    trim = match.group("trim").strip()
    base = match.group("base").strip()
    results.setdefault(trim, {}).update(results.get(base, {}))
    return trim


def parse_standard_equipment(pdf: pdfplumber.PDF) -> dict[str, dict[str, str]]:
    """Args:
        pdf: The opened CUPRA price-list PDF.

    Returns:
        `{trim: {item_name: "STANDARD"}}`, merged across every "SÉRIOVÁ
        VÝBAVA" page in the document (see module docstring) - `{}` if none
        is found.
    """
    results: dict[str, dict[str, str]] = {}
    current_trim: str | None = None

    for page in pdf.pages:
        text = page.extract_text() or ""
        title = text.splitlines()[0] if text else ""
        if _TITLE_MARKER not in title.lower():
            continue

        words = [w for w in page.extract_words(extra_attrs=["fontname", "size"]) if w["top"] > _TITLE_TOP_MAX]
        if not words:
            continue

        anchors = _cluster_columns([w["x0"] for w in words])
        columns: list[list[dict]] = [[] for _ in anchors]
        for word in words:
            columns[_nearest_column(word["x0"], anchors)].append(word)

        for column_words in columns:
            for unit_text, is_heading, size in _group_units(group_into_lines(column_words)):
                if is_heading and size >= _HEADING_SIZE_MIN:
                    current_trim = _apply_heading(unit_text, results)
                elif is_heading:
                    continue  # category heading (e.g. "Exteriér") - see module docstring
                elif current_trim is not None and unit_text:
                    results[current_trim][unit_text] = "STANDARD"

    return results

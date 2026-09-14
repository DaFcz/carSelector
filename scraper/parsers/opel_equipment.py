"""Extracts standard equipment from Opel's own "STANDARDNÍ VÝBAVA" page
(verified against all eleven fixtures: opel_corsa_cenik.pdf,
opel_corsa_electric_cenik.pdf, opel_astra_hb_cenik.pdf,
opel_astra_st_cenik.pdf, opel_astra_electric_cenik.pdf,
opel_mokka_cenik.pdf, opel_mokka_electric_cenik.pdf,
opel_frontera_cenik.pdf, opel_frontera_electric_cenik.pdf,
opel_grandland_cenik.pdf, opel_grandland_electric_cenik.pdf) - the page
right after the price table, one section per trim. Like
`dacia_equipment.py`, there's no availability matrix or price here - every
listed item is simply `STANDARD` for that trim, so
`ExtractedVariant.equipment_surcharge` is never populated by this module.
The separate "VÝBAVA NA PŘÁNÍ" (optional-equipment) pages that follow it
in every document are NOT covered: rows there are anchored by a product
code and wrap across several physical lines with no reliable way to tell
a wrapped continuation from the next row's own code apart from the same
kind of column-position reconstruction Opel's own price table needs (see
OpelParser's module docstring) - out of scope for this vertical slice.

Unlike Dacia's single-column bullet list, this page lays out TWO bullet
items per physical text line - one from a left column, one from a right
column (e.g. "• Elektronický stabilizační systém ESP • Automatická
jednozónová klimatizace" is a LEFT item and a RIGHT item sharing one
line, not one item) - verified via `page.extract_words()`: both columns'
own "•" bullets and text sit at two clearly separated, page-specific x0
bands (e.g. left ~48-60pt, right ~309-329pt on Corsa's document; ~60pt/
~321pt on Frontera's - shifts enough between documents that a hardcoded
split point would eventually misclassify a word, so `_column_threshold`
reads it fresh off each page's own bullet positions, same "positions come
from the page, never a constant" principle as `_pdf_layout.column_for_x`
and OpelParser's own `_column_anchors`). A long item name can wrap onto
the following physical line without a new bullet (verified on Frontera's
own document: "Středová konzole s držáky nápojů a flexibilním popruhem"
wraps its last word, "Intelli-Strap", onto the next line at the SAME
right-column x0, with that next line's own left column already showing a
fresh "•" bullet of its own) - `_parse_page` tracks each column's
currently-open item independently and appends a column's own bullet-less
words to it, so a wrapped tail is reattached to the right item regardless
of what the other column is doing on that same physical line.

A handful of items across Corsa/Astra HB/Astra ST/Grandland's own
combustion-plus-hybrid documents are prefixed with a "Pouze pro Hybrid:"/
"Pouze Plug-in Hybrid:" label (itself printed as its own bullet item,
verified against all four) marking every item AFTER it, in that SAME
column, as specific to that one powertrain variant of the trim - not
"standard equipment" for the trim as a whole, since the very next
`ExtractedVariant` sharing that trim can be the plain ICE row. Since
`equipment` is stored per trim, not per (trim, powertrain), these can't be
safely folded into a trim's own STANDARD set without claiming e.g. a
Plug-in Hybrid's own onboard charger is standard on the base ICE row too -
`_CONDITIONAL_RE` recognizes the label and `_parse_page` stops collecting
that column's own items for the rest of the current trim section instead
(skip rather than guess, same convention as every other brand's own
equipment module here).

Later trims are printed as a delta against an earlier one, worded "<trim>
navíc k výbavě <base trim>" (e.g. "GS navíc k výbavě Edition", "ULTIMATE
4×4 navíc k výbavě GS" on Grandland Electric's own document) - `_DELTA_RE`
matches it and `_parse_page` starts that trim's own set as a copy of the
named base trim's already-resolved set (looked up by name, not just "the
previous trim", so a reordered document would still resolve correctly)
before adding this section's own items on top - the same "STANDARD,
compounding across trims" semantics as `dacia_equipment.py`'s own delta
sections, just phrased differently in the source PDF.

Trim headings on this page don't always match `ExtractedVariant.trim`
verbatim (verified against OpelParser's own output): Astra Electric's own
page prints a bare "Edition"/"GS"/"Ultimate" even though the variant rows
for that same document carry "Edition Hatchback"/"Edition Sports Tourer"
(the body style is folded into the variant's own trim there, not printed
per trim on this page - inline "(pouze HB)"/"(pouze ST)" annotations on
individual bullet items are the only place body style shows up here), and
Grandland Electric's own delta heading spells its trim "ULTIMATE 4×4"
with a multiplication sign where OpelParser's own row reads "Ultimate
4x4" with a plain letter x (both read off the same underlying PDF, just
via different code paths - verified with `ord()` on the heading's own
character). `resolve_trim_equipment` handles both gaps: it normalizes ×
to x before comparing, and when a variant's own trim has no exact match
it retries with its trailing word(s) dropped one at a time (a generic
"strip the body-style/AWD suffix" fallback, not a hardcoded list of
suffixes - it would resolve a hypothetical future "Edition XL" against a
page that only prints "Edition" just as well as it does here)."""
from __future__ import annotations

import re

import pdfplumber

from ._pdf_layout import group_into_lines, line_text

_SECTION_TITLE_MARKER = "standardní výbava"
_LEGEND_MARKER = "popis ("
_DELTA_RE = re.compile(r"^(?P<trim>.+?)\s+navíc\s+k\s+výbavě\s+(?P<base>.+)$", re.IGNORECASE)
_CONDITIONAL_RE = re.compile(r"^pouze\b.*:$", re.IGNORECASE)
_BARE_HEADING_RE = re.compile(r"^[A-Za-zÀ-ž0-9×]+$")


def _normalize_trim(text: str) -> str:
    """Args:
        text: A trim name as printed on either this page or the price
            table (see module docstring for why the two can differ).

    Returns:
        `text` with "×" folded to a plain "x", whitespace collapsed, and
        casefolded - the form every trim-name comparison in this module
        runs against.
    """
    return re.sub(r"\s+", " ", text.replace("×", "x")).strip().casefold()


def _is_bare_trim_heading(text: str) -> bool:
    """Args:
        text: A physical line's full text, already confirmed to contain
            no bullet ("•") word.

    Returns:
        Whether `text` looks like a standalone trim heading (e.g.
        "EDITION", "Edition", "GS") rather than the page's own title,
        the trailing legend line, or an item name - a short (1-3 word)
        line of only letters/digits/×, the same shape every first trim
        heading takes across all eleven fixtures (see module docstring).
    """
    words = text.split()
    return 1 <= len(words) <= 3 and all(_BARE_HEADING_RE.match(word) for word in words)


def _column_threshold(words: list[dict]) -> float:
    """Args:
        words: One page's own `extract_words()` output.

    Returns:
        The x-position midway between the left and right bullet columns'
        own "•" glyphs - found from the largest gap between this page's
        own distinct bullet x0 values, not a hardcoded split point (see
        module docstring for why the actual split point shifts between
        documents). `0.0` if this page carries fewer than two distinct
        bullet x-positions (every word then falls in the "left" column).
    """
    bullet_xs = sorted({round(word["x0"], 1) for word in words if word["text"] == "•"})
    if len(bullet_xs) < 2:
        return 0.0
    gap_index = max(range(len(bullet_xs) - 1), key=lambda i: bullet_xs[i + 1] - bullet_xs[i])
    return (bullet_xs[gap_index] + bullet_xs[gap_index + 1]) / 2


def _parse_page(page: pdfplumber.page.Page) -> dict[str, dict[str, str]]:
    """Args:
        page: The page carrying the "STANDARDNÍ VÝBAVA" section title.

    Returns:
        `{trim: {item_name: "STANDARD"}}` for every trim section found on
        this page, each already resolved against its own delta base (see
        module docstring) and with any "Pouze ...:"-conditional items
        excluded.
    """
    lines = group_into_lines(page.extract_words())
    if not lines:
        return {}
    # Several fixtures (e.g. opel_grandland_electric_cenik.pdf) pack the
    # "ZVÝHODNĚNÉ SADY VÝBAV"/"VÝBAVA NA PŘÁNÍ" sections onto this SAME
    # page right after this one, each with its own column layout - every
    # section title on this document family ends in the literal "{sla}"
    # placeholder (verified across all eleven fixtures), so the next line
    # ending in it marks where this section's own body ends. Scoping both
    # the column-threshold computation and the row scan to lines strictly
    # between this title and that boundary keeps a later section's own
    # bullet-like glyphs from skewing `_column_threshold` (the bug this
    # scoping fixes: without it, opel_grandland_electric_cenik.pdf's
    # Edition items got sliced at the wrong x-position and merged into
    # unrelated garbage).
    end_index = next(
        (i for i, line in enumerate(lines[1:], start=1) if line_text(line).strip().endswith("{sla}")),
        len(lines),
    )
    body_lines = lines[1:end_index]
    threshold = _column_threshold([word for line in body_lines for word in line])

    trim_items: dict[str, dict[str, str]] = {}
    accumulated: dict[str, str] = {}
    current_trim: str | None = None
    columns: list[dict] = [{"buffer": [], "conditional": False}, {"buffer": [], "conditional": False}]

    def flush(index: int) -> None:
        buffer = columns[index]["buffer"]
        columns[index]["buffer"] = []
        name = " ".join(word["text"] for word in buffer).strip()
        if not name or current_trim is None:
            return
        if _CONDITIONAL_RE.match(name):
            columns[index]["conditional"] = True
            return
        if not columns[index]["conditional"]:
            accumulated[name] = "STANDARD"

    def flush_all() -> None:
        flush(0)
        flush(1)

    for line in body_lines:
        text = line_text(line).strip()
        if text.lower().startswith(_LEGEND_MARKER):
            break

        has_bullet = any(word["text"] == "•" for word in line)
        delta_match = None if has_bullet else _DELTA_RE.match(text)
        if not has_bullet and (delta_match or _is_bare_trim_heading(text)):
            flush_all()
            if current_trim is not None:
                trim_items[current_trim] = dict(accumulated)
            if delta_match:
                base_key = _normalize_trim(delta_match.group("base"))
                accumulated = dict(
                    next((items for trim, items in trim_items.items() if _normalize_trim(trim) == base_key), {})
                )
                current_trim = delta_match.group("trim").strip()
            else:
                accumulated = {}
                current_trim = text
            columns = [{"buffer": [], "conditional": False}, {"buffer": [], "conditional": False}]
            continue

        for index, column_words in enumerate((
            [word for word in line if word["x0"] < threshold],
            [word for word in line if word["x0"] >= threshold],
        )):
            if not column_words:
                continue
            if column_words[0]["text"] == "•":
                flush(index)
                columns[index]["buffer"] = column_words[1:]
            else:
                columns[index]["buffer"].extend(column_words)

    flush_all()
    if current_trim is not None:
        trim_items[current_trim] = dict(accumulated)
    return trim_items


def parse_standard_equipment(pdf: pdfplumber.PDF) -> dict[str, dict[str, str]]:
    """Args:
        pdf: The opened Opel price-list PDF.

    Returns:
        `{trim: {item_name: "STANDARD"}}` from the first page whose own
        title starts with "STANDARDNÍ VÝBAVA" (in practice exactly one
        page per fixture) - `{}` if no such page is found. Trim names are
        exactly as printed on that page (see module docstring for why
        that can differ from `ExtractedVariant.trim` - use
        `resolve_trim_equipment` to look up by the latter).
    """
    for page in pdf.pages:
        text = page.extract_text() or ""
        first_line = text.splitlines()[0].strip() if text.splitlines() else ""
        if first_line.lower().startswith(_SECTION_TITLE_MARKER):
            return _parse_page(page)
    return {}


def resolve_trim_equipment(equipment_by_trim: dict[str, dict[str, str]], trim: str) -> dict[str, str]:
    """Args:
        equipment_by_trim: This document's own result from
            `parse_standard_equipment`.
        trim: An `ExtractedVariant.trim` value to look up equipment for.

    Returns:
        `equipment_by_trim`'s entry for `trim` (compared via
        `_normalize_trim`, so a "×"/"x" spelling mismatch doesn't cause a
        miss - see module docstring), or, failing that, the entry for
        `trim` with its trailing word dropped, retried repeatedly until a
        match is found or no words remain - resolves a body-style- or
        AWD-suffixed variant trim (e.g. "Edition Hatchback", "Ultimate
        4x4") against a page that only prints the bare base trim, without
        hardcoding which suffixes exist. `{}` if nothing matches.
    """
    normalized = {_normalize_trim(trim_name): items for trim_name, items in equipment_by_trim.items()}
    words = trim.split() if trim else []
    while words:
        match = normalized.get(_normalize_trim(" ".join(words)))
        if match is not None:
            return match
        words = words[:-1]
    return {}

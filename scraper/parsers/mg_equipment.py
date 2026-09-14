"""Extracts per-trim standard equipment from MG's own two-page "VÝBAVA"
matrix (verified against all seven fixtures: mg_mg3_cenik.pdf, mg_zs_cenik
.pdf, mg_hs_cenik.pdf, mg_mgs9phev_cenik.pdf, mg_mg4ev_cenik.pdf,
mg_mgs5ev_cenik.pdf, mg_cyberster_cenik.pdf). Structurally close to
`mazda_equipment.py`'s own checkbox matrix - several category sections
(BEZPEČNOST/INTERIÉR/KOMFORT/... - not every model has the same ones) with
one column per trim and a mark per cell - but with three differences from
Mazda's own version:

1. The mark glyphs ARE consistent across every one of MG's seven fixtures:
   "•" (U+2022) for standard, "—" (U+2014) for unavailable - verified via
   `ord()` on the actual PDF characters, not by eye - both marks print as
   the same "�" replacement character in `extract_text()`/any plain
   terminal dump, since neither glyph exists in the encodings those tools
   fall back to, which is exactly why this was checked via `ord()` rather
   than assumed from what a printout looks like. Still read PER PAGE from
   that page's own trailing legend line ("• Standardní výbava — Není k
   dispozici") via `_LEGEND_RE`, the same "don't hardcode a symbol, verify
   it" discipline as Mazda's `_discover_marks` - a future MG fixture isn't
   guaranteed to keep using the same two glyphs today's seven happen to
   share, and reading the legend costs nothing since it's on every page.
   MG's own legend never names a third, "optional-in-package" mark the
   way Škoda's/Mazda's do - only these two phrases - so `equipment` here
   is only ever `"STANDARD"` or absent, never `"OPTIONAL"`/`"PACKAGE"`.
   No price appears anywhere on this matrix either (see point 3 for the
   one row where a price DOES appear, and why it's skipped rather than
   read), so `equipment_surcharge` is never populated by this module.

2. Trim column headers aren't parsed from each page's own header text at
   all - they're looked up from `MgParser`'s own already-extracted
   `ExtractedVariant.trim` values (passed in as `trims`, in the order
   `MgParser.parse` first encountered them), the same trick
   `mazda_equipment.py`'s `trims_by_model` uses and for the same reason
   (MG's price table is already the more reliable source of trim names).
   Here it doubles as the mechanism that skips MG HS's own equipment pages
   entirely: HS's own header line repeats each trim name three times
   ("EMOTION EXCLUSIVE EMOTION EXCLUSIVE EMOTION EXCLUSIVE", 6 columns) -
   verified this is a real 6-way split, not a rendering artifact, by
   reading actual per-column mark values off the page: e.g. "Automatická
   klimatizace" reads unavailable/unavailable/standard/unavailable/
   standard/unavailable across the six columns, not six copies of the
   same two values. Apparently one column per (trim, engine-group)
   combination - HS's own TGI engine comes in both a manual and an
   automatic gearbox under the same trim, alongside Hybrid+/PHEV - a
   granularity this module has no label on the page to map back onto
   `ExtractedVariant.trim` alone (nothing marks which of the three
   repeated groups is which engine, only a couple of individual ROWS
   carry an inline "(MAN)"/"(AUT)" hint). Since HS's own price-table trim
   list is just `["Emotion", "Exclusive"]` (2 names) and `_split_trailing
   _marks` requires an EXACT `len(trims)`-long run of marks at the end of
   a line, none of HS's own 6-mark rows ever matches a 2-column read -
   every row on HS's own equipment pages is silently skipped, a known,
   accepted gap (same precedent as `dacia.py`'s own Duster hybrid-
   classification gap) rather than guessing which of the three repeated
   groups a given price row's engine belongs to.

3. A handful of items wrap across more than one physical line, with the
   marks landing on a bare line of their own somewhere in the MIDDLE of
   the wrap (verified, e.g. MG3's own "Aplikace iSmart - lokalizace,
   kontrola stavu vozu, zamykání a odemykání vozu na dálku" / <marks> /
   "z chytrého telefonu") - the same shape as the wrapped-item problem
   `mazda_equipment.py`'s own docstring describes, but without that
   module's own "-" sub-bullet marker to tell a continuation line apart
   from the next item's name starting cold. Rather than guess at that
   boundary, `_parse_matrix_page` only ever reads a SELF-CONTAINED row -
   name text and its own trailing `len(trims)` marks on the exact same
   physical line, checked via `_split_trailing_marks` - and additionally
   drops any "row" whose remaining name text starts with a lowercase
   letter (`_looks_like_wrap_fragment`): pdfplumber's own tolerance-based
   line grouping (`group_into_lines`, 4pt) sometimes glues a wrapped
   continuation's tail line directly onto the marks line that precedes it
   in the source PDF (verified: "z chytrého telefonu • • • • •" comes back
   as one `group_into_lines` line), which would otherwise read as a
   syntactically valid but semantically bogus item - every genuine MG
   item name starts with an uppercase letter or a digit (verified across
   all captured items in all seven fixtures), so a lowercase first
   character reliably marks exactly these tail fragments and nothing
   else. Both checks together mean a wrapped item is skipped whole rather
   than captured under a truncated/wrong name - same "skip a row whose
   name wrapped away from its own marks rather than guess" precedent as
   `skoda_equipment.py`'s own wrapped-name rows. This also correctly skips
   ZS's one PŘÍPLATKOVÁ VÝBAVA (paid-option) row ("Elektrické střešní
   okno"), whose own last cell is a real price ("20 000 Kč") instead of a
   mark, for its one paid trim (Exclusive) only - four marks plus a price
   token, not five marks, fails `_split_trailing_marks`'s exact-count
   check the same way a wrapped-name row does, so this row is skipped
   whole rather than guessing which column the price belongs to.

Equipment pages are recognized generically, not by page number: any page
carrying MG's own "Standardní výbava .../. Není k dispozici" legend text
(`_LEGEND_RE`) is one, whether or not it also carries the big letter-
spaced "V Ý B A V A" title - only the FIRST of a document's two equipment
pages does; the second (e.g. MG3's own page 6) starts straight into its
own next category heading, no title of its own."""
from __future__ import annotations

import re

import pdfplumber

from ._pdf_layout import group_into_lines, line_text

_LEGEND_RE = re.compile(
    r"(?P<standard>\S+)\s*Standardn\S*\s+v\S*bava\s*"
    r"(?P<unavailable>\S+)\s*Nen\S*\s+k\s+dispozici",
    re.IGNORECASE,
)


def _discover_marks(lines: list[list[dict]]) -> tuple[str, str] | None:
    """Args:
        lines: One page's words already grouped into lines (see
            `_pdf_layout.group_into_lines`).

    Returns:
        `(standard_mark, unavailable_mark)`, the literal glyphs read off
        this page's own trailing legend line (see module docstring for
        why these are read per page rather than assumed), or `None` if no
        legend line was found (i.e. this isn't an equipment matrix page).
    """
    for line in lines:
        match = _LEGEND_RE.search(line_text(line))
        if match:
            return match.group("standard"), match.group("unavailable")
    return None


def _looks_like_wrap_fragment(name: str) -> bool:
    """Args:
        name: The name text recovered in front of a row's trailing marks.

    Returns:
        `True` if `name` starts with a lowercase letter - the signature
        of a wrapped item's tail line having glued itself onto that
        item's own marks line (see module docstring, point 3) rather than
        a genuine item name, which always starts uppercase or with a
        digit in every one of the seven fixtures.
    """
    return bool(name) and name[0].isalpha() and name[0].islower()


def _split_trailing_marks(
    line: list[dict], column_count: int, marks_vocab: tuple[str, str]
) -> tuple[list[dict], list[dict] | None]:
    """Args:
        line: One line's words.
        column_count: Number of trim columns on this page (`len(trims)`).
        marks_vocab: This page's own `(standard, unavailable)` mark
            glyphs (see `_discover_marks`).

    Returns:
        `(name_tokens, marks)` - `marks` is `line`'s trailing run of marks
        tokens if that run is EXACTLY `column_count` long (not merely at
        least that long - see module docstring, point 2, for why HS's own
        6-mark rows must be rejected rather than partially matched against
        a 2-trim list), else `None` (the whole `line` is `name_tokens`,
        unchanged).
    """
    run_length = 0
    for word in reversed(line):
        if word["text"] in marks_vocab:
            run_length += 1
        else:
            break
    if run_length != column_count:
        return line, None
    return line[:-column_count], line[-column_count:]


def _parse_matrix_page(
    lines: list[list[dict]], trims: list[str], marks_vocab: tuple[str, str]
) -> dict[str, dict[str, str]]:
    """Args:
        lines: One equipment page's lines (category headers, item rows,
            and its own trailing legend line all included - each is
            filtered out here as it's encountered rather than by the
            caller).
        trims: This document's trim names in column order (see module
            docstring, point 2).
        marks_vocab: This page's own `(standard, unavailable)` mark
            glyphs (see `_discover_marks`).

    Returns:
        `{trim: {item_name: "STANDARD"}}` - only cells matching this
        page's own standard mark; unavailable cells and any row that
        can't be confidently read (see module docstring, point 3) are
        skipped rather than guessed.
    """
    standard_mark = marks_vocab[0]
    column_count = len(trims)
    result: dict[str, dict[str, str]] = {trim: {} for trim in trims}

    for line in lines:
        if _LEGEND_RE.search(line_text(line)):
            continue
        name_tokens, marks = _split_trailing_marks(line, column_count, marks_vocab)
        if marks is None:
            continue
        item_name = line_text(name_tokens).strip()
        if not item_name or _looks_like_wrap_fragment(item_name):
            continue
        for trim, mark in zip(trims, marks):
            if mark["text"] == standard_mark:
                result[trim][item_name] = "STANDARD"

    return result


def parse_equipment(pdf: pdfplumber.PDF, trims: list[str]) -> dict[str, dict[str, str]]:
    """Args:
        pdf: The opened MG price-list PDF.
        trims: This document's one model's trim names, in the exact
            order/casing `MgParser` already produced for
            `ExtractedVariant.trim` (see module docstring, point 2, for
            why these come from the price table rather than being parsed
            off an equipment page's own header).

    Returns:
        `{trim: {item_name: "STANDARD"}}`, merged across every equipment
        matrix page found (see `_discover_marks` for how such a page is
        recognized) - `{}` for `trims` with no matching page, or whose
        equipment pages' own column count never matches `len(trims)` (see
        module docstring, point 2 - MG HS today).
    """
    result: dict[str, dict[str, str]] = {trim: {} for trim in trims}

    for page in pdf.pages:
        lines = group_into_lines(page.extract_words())
        marks_vocab = _discover_marks(lines)
        if marks_vocab is None:
            continue
        page_equipment = _parse_matrix_page(lines, trims, marks_vocab)
        for trim, items in page_equipment.items():
            result.setdefault(trim, {}).update(items)

    return result

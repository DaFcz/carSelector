"""Extracts per-trim standard equipment from Hyundai's own "Přehled hlavních
prvků stupňů výbav" equipment section (verified against all six fixtures:
hyundai_i20_cenik.pdf, hyundai_i30_cenik.pdf, hyundai_kona_cenik.pdf,
hyundai_santa_fe_cenik.pdf, hyundai_tucson_cenik.pdf, hyundai_tucson_hev_
phev_cenik.pdf). Unlike that section's own OWN first page (a free-text
"Hlavní prvky výbavy Start: ... Comfort a navíc: ..." bullet overview,
structurally identical to Dacia's - not parsed here, since everything on it
is repeated, item for item, in the structured matrix that follows), the
following 2-3 pages hold a real per-category availability matrix: one
column per trim, a mark per cell -

    Tónované čelní sklo + tónovaná přední okna - ● ● ●

Like Škoda's "Samostatné prvky výbavy" page (`skoda_equipment.py`), a row is
split into (name, mark run) by finding a contiguous run of mark tokens
(here "●"/"-"/"–" instead of Škoda's "●"/"–") - but from the RIGHT end of
the line, not the first occurrence like Škoda's `_split_row`: Hyundai's own
item descriptions use a bare hyphen/en-dash as ordinary punctuation
mid-phrase (e.g. "Inteligentní adaptivní tempomat - pouze s DCT", "ECS –
pouze s motory MHEV 48V"), so scanning from the first mark-looking token
would misfire on that descriptive dash and split the row in the wrong
place. Scanning backward from the last token instead only ever picks up
the REAL trailing availability cells (verified: every real row's mark run
is the very end of the line, nothing ever trails after it) and stops the
instant a non-mark word is hit, so a punctuation dash buried earlier in the
name is never reached.

The column count itself is never hardcoded - like Škoda, it's read off the
first row found with a plausible (>=2) mark run, and every later row's own
run must match that count exactly or it's skipped (see `parse_equipment`).
This one rule alone also handles Hyundai's OWN "package-only" cells
without any extra vocabulary: some cells hold a package name instead of a
mark (a bare "PREMIUM"/"CLUB"/"TECHNOLOGY", or even a compound "+/●"/"-/-"
pair on Santa Fe's two multi-seat-count rows) rather than "●"/"-" - since
that token isn't itself a recognized mark character, it's never part of
the trailing run, so the whole row's run comes out short (or the row's
trailing token doesn't match at all) and gets skipped rather than guessed
at - no attempt is made to tell "PACKAGE" apart from "the row just isn't
readable", since the item's OWN name text can't be reliably recovered
either once a package-name token has swallowed one of its trailing marks.

Trim names for each page's matrix come from that SAME page's own header
block (the 1-3 physical lines above the first category heading -
"Vnější výbava"/"Vnitřní výbava"/"Bezpečnost a asistenční systémy"/
"Komfortní výbava"/"Audiosytémy a konektivita", the fixed heading vocabulary
verified across all six fixtures), read PER PAGE rather than once per
document since the running header repeats on every equipment page (same
"read the header fresh each time" precedent as Mazda's per-page legend).
Multi-word trim names ("N Line Style", "Premium Luxury") often wrap across
2-3 of those physical header lines rather than sitting on one (Tucson's
own header prints "Premium" and "N Line" on line 1, "Comfort"/"Smart"/
"N Line" on line 2, and "Luxury"/"Premium" on line 3 - each column's own
words stacked at the same x0, not joined by whitespace on one line) - so,
like Škoda's rotated-header labels, header words are assigned to the
nearest column x-position DERIVED FROM THE DATA ROWS (the column_x already
established from the first clean mark run), not the other way around, then
read top-to-bottom (not Škoda's bottom-to-top, since these characters
aren't rotated) to reassemble each column's full label.

Like Škoda's "Samostatné prvky výbavy" page, an item whose OWN name wraps
across physical lines (common here - Hyundai wraps far more aggressively
than Škoda, e.g. "Antiblokovací brzdový systém ABS + ... brzdový" / "● ● ●
●" / "asistent BA + ... MCB" across three separate lines with the marks
landing on the MIDDLE one) is skipped, not reconstructed: the line
carrying the mark run has no name text in front of it (`name_tokens` comes
out empty), so - same "better to have fewer items without guessing than an
invented/misassigned name" stance as `skoda_equipment.py` - it's dropped
rather than stitched together from neighboring lines, which would risk
silently absorbing an unrelated line's text (see the punctuation-dash
problem above) into the wrong item.

No cell anywhere on this section carries its own price (unlike Škoda's
"Samostatné prvky výbavy" - these are standard-equipment-per-trim
matrices, not paid add-ons), so `ExtractedVariant.equipment_surcharge` is
never populated by this module, same as `dacia_equipment.py`/
`mazda_equipment.py`.

Known gap: Santa Fe's fixture covers two separate price lists (HEV, page 1;
PHEV, page 8 - see `hyundai.py`'s module docstring) each with their OWN
equipment section further down the same PDF (pages 3-5 and 10-12
respectively), and both sections use the same trim names ("Comfort"/
"Smart"/"Style"/"Calligraphy" for the HEV section, "Comfort"/"Style"/
"Calligraphy" - no Smart - for the PHEV one). Since `ExtractedVariant` has
no powertrain-specific equipment key, `parse_equipment`'s result is keyed
by trim name alone and merges both sections' items into the same trim
bucket - a real, accepted gap (same class as Dacia's hybrid
classification note in `dacia.py`) rather than a silently wrong "fix": if
the two sections ever disagreed on a given trim's item, the later section
in document order would win.
"""
from __future__ import annotations

import pdfplumber

from ._pdf_layout import group_into_lines, line_text

_CATEGORY_MARKERS = {
    "Vnější výbava",
    "Vnitřní výbava",
    "Bezpečnost a asistenční systémy",
    "Komfortní výbava",
    "Audiosytémy a konektivita",
}
_STANDARD_MARK = "●"
_UNAVAILABLE_MARKS = {"-", "–"}
_MARK_CHARS = _UNAVAILABLE_MARKS | {_STANDARD_MARK}


def _is_equipment_page(lines: list[list[dict]]) -> int | None:
    """Args:
        lines: One page's words, already grouped into lines (see
            `_pdf_layout.group_into_lines`).

    Returns:
        The index of the first line whose text is one of
        `_CATEGORY_MARKERS`, or `None` if this page isn't part of the
        equipment matrix section at all (e.g. the price table, the
        free-text overview page, or the "Příplatková výbava" appendix
        page, which uses a different, non-matrix layout - see module
        docstring for why that page isn't handled here).
    """
    return next((i for i, line in enumerate(lines) if line_text(line).strip() in _CATEGORY_MARKERS), None)


def _trailing_mark_run(line: list[dict]) -> tuple[list[dict], list[dict]]:
    """Args:
        line: One line's words, left to right.

    Returns:
        `(name_tokens, mark_tokens)` - `mark_tokens` is the trailing
        contiguous run of tokens whose text is "●"/"-"/"–" (possibly
        empty, if the line doesn't end in one), `name_tokens` everything
        before it. See module docstring for why this scans from the RIGHT
        rather than finding the first mark-like token, the way
        `skoda_equipment._split_row` does.
    """
    split_at = len(line)
    while split_at > 0 and line[split_at - 1]["text"] in _MARK_CHARS:
        split_at -= 1
    return line[:split_at], line[split_at:]


def _assign_header_labels(header_lines: list[list[dict]], column_x: list[float]) -> list[str]:
    """Args:
        header_lines: The physical header lines above a matrix page's
            first category heading (1-3 lines - see module docstring for
            why a multi-word trim name can be split across several of
            them).
        column_x: This page's own column x-positions, derived from its
            first clean mark run (see `parse_equipment`).

    Returns:
        One assembled, uppercased label per `column_x` entry (uppercased
        to match `HyundaiParser`'s own price-table `trim` values, e.g.
        "N LINE STYLE") - words are bucketed by nearest `column_x` entry,
        then read top to bottom within each bucket (these header
        characters aren't rotated, unlike Škoda's, so no bottom-to-top
        reversal is needed).
    """
    buckets: list[list[dict]] = [[] for _ in column_x]
    for line in header_lines:
        for token in line:
            nearest = min(range(len(column_x)), key=lambda i: abs(column_x[i] - token["x0"]))
            buckets[nearest].append(token)
    labels = []
    for bucket in buckets:
        bucket.sort(key=lambda t: t["top"])
        labels.append(" ".join(t["text"] for t in bucket).strip().upper())
    return labels


def parse_equipment(pdf: pdfplumber.PDF) -> dict[str, dict[str, str]]:
    """Args:
        pdf: The opened Hyundai price-list PDF.

    Returns:
        `{trim: {item_name: "STANDARD"}}`, merged across every equipment
        matrix page found (see module docstring for the known Santa Fe
        HEV/PHEV merge gap) - `trim` uppercased to match
        `ExtractedVariant.trim`. `{}` for a document with no matching
        page (or a page whose first mark run can't be trusted - fewer
        than 2 tokens).
    """
    result: dict[str, dict[str, str]] = {}

    for page in pdf.pages:
        lines = group_into_lines(page.extract_words())
        marker_idx = _is_equipment_page(lines)
        if marker_idx is None:
            continue

        header_lines, body_lines = lines[:marker_idx], lines[marker_idx:]

        column_x: list[float] | None = None
        data_rows: list[tuple[list[dict], list[dict]]] = []
        for line in body_lines:
            name_tokens, mark_tokens = _trailing_mark_run(line)
            if not mark_tokens:
                continue
            if column_x is None:
                if len(mark_tokens) < 2:
                    continue
                column_x = [t["x0"] for t in mark_tokens]
            if len(mark_tokens) != len(column_x):
                continue
            if not name_tokens:
                continue  # the item's name wrapped onto another line - see module docstring
            data_rows.append((name_tokens, mark_tokens))

        if column_x is None:
            continue

        trims = _assign_header_labels(header_lines, column_x)
        for trim in trims:
            result.setdefault(trim, {})

        for name_tokens, mark_tokens in data_rows:
            item_name = line_text(name_tokens).strip()
            if not item_name:
                continue
            for trim, token in zip(trims, mark_tokens):
                if token["text"] == _STANDARD_MARK:
                    result[trim][item_name] = "STANDARD"

    return result

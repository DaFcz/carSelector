"""Extracts standard equipment and colors from CUPRA's own "SÉRIOVÁ
VÝBAVA" and "BARVY" pages (verified word-by-word via `page.extract_words
(extra_attrs=["fontname", "size"])` against all six fixtures: cupra_born
_cenik.pdf, cupra_formentor_cenik.pdf, cupra_leon_cenik.pdf, cupra_leon
_sportstourer_cenik.pdf, cupra_raval_cenik.pdf, cupra_terramar_cenik.pdf).

**Equipment.** Every "SÉRIOVÁ VÝBAVA" page lays items out as a 2-4 column
newspaper grid - font tells the three row kinds apart unambiguously
(`Montserrat-SemiBold` size ~10pt = a trim heading, `Montserrat-SemiBold`
size ~8pt = a category heading like "Exteriér"/"Bezpečnost a asistenční
systémy" - read and discarded, nothing downstream needs the category -
and `Montserrat-Regular`/`-Thin` size ~8pt = an actual item). No price
ever appears on this page (paid extras live on a separate "VÝBAVA NA
PŘÁNÍ" page, not covered here - see `parse_colors` below for the one
place CUPRA's optional pricing IS captured), so every item is `STANDARD`
and `equipment_surcharge` is never populated by this module.

A trim's own section spans MULTIPLE columns and pages without ever
re-declaring itself at the top of each one (verified on Formentor's own
document: column 3 of page 4 opens mid-column with more "VZ" items - no
heading of its own - carried over from column 2's "VZ /navíc oproti
výbavě CUPRA" heading earlier on the SAME page, until a fresh "VZ Extreme
/navíc oproti výbavě CUPRA" heading appears partway down that same
column). Reading order is therefore COLUMN-MAJOR: every row belonging to
column 1 (top to bottom), then every row belonging to column 2, and so
on - `_page_rows` derives that order by first grouping words into
physical lines (`_group_lines`, a tight top-tolerance - two lines from
DIFFERENT columns can share the exact same `top`, e.g. every column's own
heading row lines up at the same `top` its neighbours' headings do), then
splitting each line into per-column PIECES wherever the gap to the
previous word's `x1` exceeds `_COLUMN_SPLIT_GAP`, then clustering every
piece's own starting `x0` into a handful of stable per-page column
anchors and assigning each WHOLE piece (never an individual word - two
words within the SAME piece can legitimately sit closer to the NEXT
column's anchor than their own, verified on Formentor's own "VZ /navíc
oproti výbavě CUPRA" heading, whose last word numerically favours the
neighbouring column despite the gap in front of it being an entirely
ordinary ~7pt word space) to its nearest one. `_COLUMN_SPLIT_GAP` sits
comfortably between that ordinary word spacing and the smallest real
column gap actually observed (~53pt - a column-2 heading ending shortly
before column 4's own next category heading begins on a nearly-identical
`top`).

A trim heading is either bare (this trim's own complete list - e.g.
"Tribe", "CUPRA" the first time it appears) or "<TRIM> /navíc oproti
výbavě <OTHER>" (only what's added on top of an explicitly named other
trim - never assumed to be "whatever came right before": Formentor's own
"VZ Extreme" and Raval's own "ENDURANCE" are both deltas against CUPRA's
base trim even though a DIFFERENT trim's section sits physically between
them). `_apply_heading` looks `OTHER` up directly in the `results` dict
built so far. Seeing the SAME trim name again (no name change from
`current_trim`) is just this trim's own section continuing onto a new
column/page - not a second, independent bare heading - so it does NOT
reset that trim's accumulated items; only an actual name change does.

An item can itself wrap onto a second physical line with no punctuation
cue (verified: Terramar's own "Nastavitelné bederní opěrky pro přední
sedadla" / "(neplatí pro vozy s manuální převodovkou)" pair) - the
continuation line's own top-gap from the previous line, within the SAME
column, is always well under `_CONTINUATION_GAP_MAX` (~13pt - also
comfortably covers a wrapped TRIM heading's own ~12pt gap, e.g.
Formentor's own "VZ Extreme /navíc oproti výbavě" / "CUPRA" pair) while
the gap to the NEXT item's own first line is always bigger (~19pt+) -
`parse_standard_equipment`'s own item buffer uses that gap alone, the
same principle `mazda_equipment.py`/`peugeot_equipment.py` already rely
on for their own wrapped rows - flushed into `results` as soon as it
ends (not deferred to the end of the page), since a LATER trim heading
on the same page that copies THIS trim's items (see `_apply_heading`)
must see them already there.

**Colors.** Every "BARVY" page is a flat single-column list (name - code
   price) with one `` (included) / `` (priced option) mark
per trim column - ``/`` are Private-Use-Area icon-font glyphs,
the SAME shape `peugeot_equipment.py` already found on Peugeot's own
pages, confirmed here via `ord()` too. A cell with NEITHER glyph (not
even a dash) means that color isn't offered on that trim - simply absent,
not marked. Column TRIM NAMES aren't read from the page's own rotated
header (its letters are individually reversed per word, "ARPUC" for
"CUPRA", "ebirT" for "Tribe" - readable, but multi-word trims stack their
words vertically in an order that isn't reliably top-to-bottom, e.g.
Formentor's own "Tribe VZ" column prints "VZ" above "Tribe" - so instead
of decoding that, `parse_colors` consumes trims from `CupraParser`'s own
already-extracted, already-correctly-ordered trim list, N at a time (N =
however many mark columns this specific BARVY page actually has) in the
SAME order the price table introduced them: verified across all three of
Formentor's own BARVY pages (3 columns -> CUPRA/VZ/VZ Extreme, 2 columns
-> Tribe/Tribe VZ, 1 column -> VZ5) - a BARVY page always immediately
follows the price/equipment pages for the trim group it prices, so this
sequential consumption lines up without needing to parse the header text
at all."""
from __future__ import annotations

import re

import pdfplumber

_ROW_GAP = 1.5  # pt; words on the same physical line land within this of each other
_ANCHOR_CLUSTER_GAP = 100.0  # pt; used to merge per-piece start x0s into stable column anchors
_COLUMN_SPLIT_GAP = 35.0  # pt; comfortably between ordinary word spacing (~3-10pt) and a real column gap (~53pt+)
_CONTINUATION_GAP_MAX = 13.0  # pt; wrapped-line gap within one item/heading vs. ~19pt+ between items
_TRIM_HEADING_MIN_SIZE = 9.5
_DELTA_MARKER = " /navíc oproti výbavě "

_INCLUDED_MARK = ""
_OPTIONAL_MARK = ""
_NAME_MAX_X0 = 260.0
_MARK_MIN_X0 = 280.0
_MARK_MAX_X0 = 600.0  # pt; excludes a second, unexplained mark-glyph cluster some BARVY pages carry far to the right (~700+)
_PRICE_TOKEN_RE = re.compile(r"^[\d ]+$")


def _group_lines(words: list[dict]) -> list[list[dict]]:
    words = sorted(words, key=lambda w: w["top"])
    lines: list[list[dict]] = [[words[0]]]
    for word in words[1:]:
        if word["top"] - lines[-1][-1]["top"] <= _ROW_GAP:
            lines[-1].append(word)
        else:
            lines.append([word])
    return lines


def _split_by_gap(words: list[dict], gap: float) -> list[list[dict]]:
    words = sorted(words, key=lambda w: w["x0"])
    clusters: list[list[dict]] = [[words[0]]]
    for word in words[1:]:
        if word["x0"] - clusters[-1][-1]["x1"] > gap:
            clusters.append([word])
        else:
            clusters[-1].append(word)
    return clusters


def _cluster_anchors(values: list[float], gap: float) -> list[float]:
    values = sorted(values)
    clusters: list[list[float]] = [[values[0]]]
    for v in values[1:]:
        if v - clusters[-1][-1] > gap:
            clusters.append([v])
        else:
            clusters[-1].append(v)
    return [min(c) for c in clusters]


def _nearest_index(x0: float, anchors: list[float]) -> int:
    return min(range(len(anchors)), key=lambda i: abs(anchors[i] - x0))


def _page_rows(words: list[dict]) -> list[tuple[int, float, list[dict]]]:
    """Args:
        words: `page.extract_words(extra_attrs=["fontname", "size"])` for
            one page, already filtered to below the page title.

    Returns:
        `(column_index, top, line_words)` for every physical line on the
        page, in column-major reading order (see module docstring).
    """
    # Two words within the SAME logical line can legitimately be closer to
    # the NEXT column's anchor than their own (verified: Formentor's own
    # "VZ /navíc oproti výbavě CUPRA" heading has its last word, "CUPRA",
    # sitting numerically nearer column 3's anchor than column 2's - yet
    # the actual gap in front of it is a completely ordinary ~7pt word
    # space) - so words are never assigned to a column one at a time.
    # Instead, `_group_lines` groups by `top` first (two DIFFERENT
    # columns' own lines can share the exact same `top`, e.g. every
    # column's heading row lines up with its neighbours'), then each
    # top-group is split into pieces wherever the gap to the previous
    # word's `x1` exceeds `_COLUMN_SPLIT_GAP` - a real column boundary
    # (verified minimum: ~53pt, a column-2 heading ending shortly before
    # column 4's next category heading begins) is always several times
    # wider than an ordinary word-to-word gap (~3-10pt), so a threshold
    # comfortably between the two splits every real boundary without
    # ever splitting inside one column's own line.
    pieces = [cluster for line in _group_lines(words) for cluster in _split_by_gap(line, _COLUMN_SPLIT_GAP)]
    anchors = _cluster_anchors([min(w["x0"] for w in piece) for piece in pieces], _ANCHOR_CLUSTER_GAP)

    by_column: dict[int, list[dict]] = {}
    for piece in pieces:
        column = _nearest_index(min(w["x0"] for w in piece), anchors)
        by_column.setdefault(column, []).extend(piece)

    indexed: list[tuple[int, float, list[dict]]] = []
    for column, column_words in by_column.items():
        for line in _group_lines(column_words):
            indexed.append((column, line[0]["top"], line))

    indexed.sort(key=lambda t: (t[0], t[1]))
    return indexed


def _is_trim_heading(line_words: list[dict]) -> bool:
    first = line_words[0]
    return "SemiBold" in first.get("fontname", "") and first.get("size", 0) >= _TRIM_HEADING_MIN_SIZE


def _is_category_heading(line_words: list[dict]) -> bool:
    first = line_words[0]
    return "SemiBold" in first.get("fontname", "") and first.get("size", 0) < _TRIM_HEADING_MIN_SIZE


def _apply_heading(text: str, results: dict[str, dict[str, str]], current_trim: str | None) -> str:
    """Args:
        text: A trim-heading line's full text, e.g. "CUPRA" or "VZ
            Extreme /navíc oproti výbavě CUPRA".
        results: Trims accumulated so far - mutated in place (a new trim
            name gets an entry seeded from its referenced base, if any).
        current_trim: The trim in effect immediately before this heading.

    Returns:
        The trim now in effect. Unchanged (and `results` untouched) if
        `text` just restates `current_trim` - a column/page boundary, not
        a real transition (see module docstring).
    """
    if _DELTA_MARKER in text:
        trim, base = text.split(_DELTA_MARKER, 1)
        trim, base = trim.strip(), base.strip()
    else:
        trim, base = text.strip(), None

    if trim == current_trim:
        return current_trim

    results[trim] = dict(results[base]) if base in results else {}
    return trim


def _line_text(line_words: list[dict]) -> str:
    return " ".join(w["text"] for w in sorted(line_words, key=lambda w: w["x0"])).strip()


def parse_standard_equipment(pdf: pdfplumber.PDF) -> dict[str, dict[str, str]]:
    """Args:
        pdf: The opened CUPRA price-list PDF.

    Returns:
        `{trim: {item_name: "STANDARD"}}`, merged across every "SÉRIOVÁ
        VÝBAVA" page found, each higher/delta trim already including its
        referenced base trim's items (see module docstring).
    """
    results: dict[str, dict[str, str]] = {}
    current_trim: str | None = None

    for page in pdf.pages:
        text = page.extract_text() or ""
        if not text.splitlines() or "SÉRIOVÁ VÝBAVA" not in text.splitlines()[0].upper():
            continue

        words = [w for w in page.extract_words(extra_attrs=["fontname", "size"]) if w["top"] > 40]
        if not words:
            continue

        heading_buffer: list[str] = []
        heading_column: int | None = None
        heading_top: float | None = None
        item_buffer: list[str] = []
        item_key: tuple[str, int] | None = None
        item_top: float | None = None

        def flush_heading() -> None:
            nonlocal current_trim, heading_buffer, heading_column, heading_top
            if heading_buffer:
                current_trim = _apply_heading(" ".join(heading_buffer), results, current_trim)
            heading_buffer = []
            heading_column = None
            heading_top = None

        def flush_item() -> None:
            # Written into `results` immediately (not deferred to the end
            # of the page) so a LATER trim heading on this same page that
            # copies THIS trim's items (see `_apply_heading`) sees them
            # already there - column 0's "CUPRA" items must be in
            # `results["CUPRA"]` by the time column 1's "VZ /navíc oproti
            # výbavě CUPRA" heading is reached, not just buffered.
            nonlocal item_buffer, item_key, item_top
            if item_buffer and item_key is not None:
                name = " ".join(item_buffer).strip()
                if name:
                    results[item_key[0]][name] = "STANDARD"
            item_buffer = []
            item_key = None
            item_top = None

        for column, top, line_words in _page_rows(words):
            if _is_category_heading(line_words):
                flush_heading()
                flush_item()
                continue
            if _is_trim_heading(line_words):
                flush_item()
                # A heading can itself wrap onto a second physical line
                # with no marker of its own (see module docstring) -
                # buffered and merged the same way a wrapped ITEM is,
                # only applied once a non-heading row (or a column/gap
                # break) confirms the heading is actually finished.
                line_text = _line_text(line_words)
                if heading_buffer and column == heading_column and top - heading_top <= _CONTINUATION_GAP_MAX:
                    heading_buffer.append(line_text)
                else:
                    flush_heading()
                    heading_buffer = [line_text]
                    heading_column = column
                heading_top = top
                continue

            flush_heading()
            if current_trim is None:
                continue
            text = _line_text(line_words)
            if not text:
                continue
            key = (current_trim, column)
            if key == item_key and item_top is not None and top - item_top <= _CONTINUATION_GAP_MAX:
                item_buffer.append(text)
            else:
                flush_item()
                item_buffer = [text]
                item_key = key
            item_top = top

        flush_heading()
        flush_item()

    return results


def parse_colors(
    pdf: pdfplumber.PDF, trims_in_order: list[str]
) -> dict[str, dict[str, tuple[dict[str, str], dict[str, float]]]]:
    """Args:
        pdf: The opened CUPRA price-list PDF.
        trims_in_order: Every trim this document covers, in the exact
            order `CupraParser` first encountered them in the price
            table - see module docstring for why BARVY pages consume
            from this list sequentially instead of parsing their own
            rotated header text.

    Returns:
        `{trim: (colors, color_surcharge)}` - `colors` maps a color name
        to `"STANDARD"`/`"OPTIONAL"`, `color_surcharge` holds the price
        (CZK) for each `"OPTIONAL"` color on that trim. A trim with no
        BARVY page coverage at all is simply absent.
    """
    result: dict[str, dict[str, tuple[dict[str, str], dict[str, float]]]] = {}
    remaining = list(trims_in_order)

    for page in pdf.pages:
        text = page.extract_text() or ""
        if not text.splitlines() or "BARVY" not in text.splitlines()[0].upper():
            continue

        # top > 100 also drops the page's own rotated trim-name header row
        # (top ~69-79) - its own text sits at x0 >= _MARK_MIN_X0 too (the
        # same column band as real mark cells) and would otherwise pollute
        # `mark_words` with non-data rows.
        words = [w for w in page.extract_words() if w["top"] > 100]
        if not words:
            continue

        name_words = [w for w in words if w["x0"] < _NAME_MAX_X0]
        mark_words = [w for w in words if _MARK_MIN_X0 <= w["x0"] < _MARK_MAX_X0]
        if not mark_words:
            continue

        # Column anchors are seeded from the mark GLYPHS only (never a
        # price's own digit/"Kč" tokens, which sit further right on the
        # SAME row and would otherwise inflate the count - see module
        # docstring for why a color's price is one shared trailing value
        # for the row, not a value per trim column).
        glyph_words = [w for w in mark_words if w["text"] in (_INCLUDED_MARK, _OPTIONAL_MARK)]
        if not glyph_words:
            continue
        anchors = _cluster_anchors(sorted({w["x0"] for w in glyph_words}), 15.0)
        column_count = len(anchors)
        if column_count == 0 or column_count > len(remaining):
            continue
        trims = remaining[:column_count]
        remaining = remaining[column_count:]
        for trim in trims:
            result.setdefault(trim, ({}, {}))

        name_lines = _group_lines(sorted(name_words, key=lambda w: w["top"]))
        name_by_top = {ln[0]["top"]: " ".join(w["text"] for w in sorted(ln, key=lambda w: w["x0"])) for ln in name_lines}

        mark_rows = _group_lines(sorted(mark_words, key=lambda w: w["top"]))
        for row in mark_rows:
            row_top = row[0]["top"]
            owner_top = max((t for t in name_by_top if t <= row_top + 3), default=None)
            if owner_top is None:
                continue
            color_name = name_by_top[owner_top]

            # Glyph words need no clustering at all - `extract_words()`
            # already returns each ``/`` as its own word, and
            # two glyphs sitting in adjacent columns can be as little as
            # ~12pt apart edge-to-edge (verified - narrower than a normal
            # word gap, since the glyph itself has almost no width), too
            # close for any general-purpose gap threshold to separate
            # reliably. Only the row's price tokens (digits/"Kč", always
            # to the right of every mark) are clustered, into one SHARED
            # value that applies to every trim this row marked "optional"
            # (see module docstring - CUPRA doesn't disclose a different
            # price per trim for the same color).
            price_words = [w for w in row if w["text"] not in (_INCLUDED_MARK, _OPTIONAL_MARK)]
            shared_price: float | None = None
            if price_words:
                price_texts = [w["text"] for w in sorted(price_words, key=lambda w: w["x0"])]
                digit_texts = [t for t in price_texts if t != "Kč"]
                if digit_texts and all(_PRICE_TOKEN_RE.match(t) for t in digit_texts):
                    digits = "".join(digit_texts).replace(" ", "")
                    if digits.isdigit():
                        shared_price = float(digits)

            for word in row:
                if word["text"] not in (_INCLUDED_MARK, _OPTIONAL_MARK):
                    continue
                idx = _nearest_index(word["x0"], anchors)
                if idx >= len(trims):
                    continue
                trim = trims[idx]
                colors, surcharge = result[trim]
                if word["text"] == _INCLUDED_MARK:
                    colors[color_name] = "STANDARD"
                    surcharge.pop(color_name, None)
                elif shared_price is not None:
                    colors[color_name] = "OPTIONAL"
                    surcharge[color_name] = shared_price

    return result

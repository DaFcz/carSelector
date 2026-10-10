"""Extracts optional equipment from the "Samostatné prvky výbavy" page
("Standalone equipment items", Škoda price list) — individual paid
add-ons (tow hitch, alarm, ...) with an availability matrix per trim
level and a price.

Vertical slice: just this one page. "Pakety" ("Packages") have the same
matrix format, but the package name is interleaved with a multi-line
bullet-point description between the heading and the data row — a
separate, harder step, see the plan. The "Essence"/"Selection (in
addition to...)" trims are flat text without a table and aren't handled
here at all.

Row format (`page.extract_words()` grouped into lines, see
`_pdf_layout.group_into_lines`):

    Příprava pro tažné zařízení ● ● ● ● ● ● ● ● 5 000

The trim-level column headers are ROTATED (90°) in the PDF — read via
`_pdf_layout.group_rotated_chars_into_columns`. Their x-position doesn't
exactly match the x-position of the dots/dashes in the data rows though
(see `_assign_column_labels` — that's why labels are assigned to the
nearest column DERIVED FROM THE DATA ROW, not the other way around).

Items whose name wraps across multiple lines in the PDF (typically for
longer phrases, e.g. "Elektrická přední sedadla s pamětí a zrcátka s
osvětlením nástupního prostoru") are skipped — the data row with the
dots/dashes then has no text in front of it and `item_name` comes out
empty. Better to have fewer items without guessing than an invented/
misassigned name."""
from __future__ import annotations

import pdfplumber

from ._pdf_layout import group_into_lines, group_rotated_chars_into_columns

_SECTION_TITLE = "Samostatné prvky výbavy"
_AVAILABLE = "●"
_UNAVAILABLE = "–"
_AVAILABILITY_SYMBOLS = (_AVAILABLE, _UNAVAILABLE)


def _split_row(line: list[dict]) -> tuple[list[dict], list[dict], list[dict]] | None:
    """Splits a row into (name, availability symbols, price). None if the
    row doesn't contain a contiguous block of ●/– symbols (i.e. it's not a data row)."""
    avail_start = next((i for i, w in enumerate(line) if w["text"] in _AVAILABILITY_SYMBOLS), None)
    if avail_start is None:
        return None

    avail_end = avail_start
    while avail_end < len(line) and line[avail_end]["text"] in _AVAILABILITY_SYMBOLS:
        avail_end += 1

    return line[:avail_start], line[avail_start:avail_end], line[avail_end:]


def _assign_column_labels(raw_labels: list[dict], column_x: list[float]) -> list[str]:
    """Assigns labels from the rotated header (see module docstring) to the
    nearest column derived from the data row. Multi-word trim names (Top
    Selection/Exclusive Selection) have both words closer to each other
    than to the neighboring column, so they merge on their own this way —
    no need to hardcode specific names like in
    `skoda_ice._merge_same_line_trim_tokens`."""
    buckets: list[list[str]] = [[] for _ in column_x]
    for label in raw_labels:
        nearest = min(range(len(column_x)), key=lambda i: abs(column_x[i] - label["x0"]))
        buckets[nearest].append(label["text"].strip())
    return [" ".join(b) for b in buckets]


def _parse_price(price_tokens: list[dict]) -> float | None:
    """Args:
        price_tokens: The tokens trailing the availability symbols on a
            data row (see `_split_row`) - normally a single "Kč with DPH"
            amount using a space as the thousands separator (e.g.
            `"5 000"`, `"25 000"`).

    Returns:
        The amount as a float, or `None` if `price_tokens` doesn't reduce
        to a plain integer (e.g. the row's price wrapped onto another
        line, same class of gap as a wrapped item name - see module
        docstring) - never fabricated.
    """
    digits = "".join(t["text"] for t in price_tokens).replace(" ", "").replace("\xa0", "")
    return float(digits) if digits.isdigit() else None


def parse_standalone_equipment(
    pdf: pdfplumber.PDF,
) -> tuple[dict[str, dict[str, str]], dict[str, float]]:
    """Returns `({trim_level: {item_name: "OPTIONAL"}}, {item_name: price_czk})`
    from the "Samostatné prvky výbavy" page. An item always has a non-zero
    price (it's a paid add-on), so it's always `OPTIONAL`, never
    `STANDARD` - and the price is the same regardless of trim (one price
    column per item, not per trim), hence the separate flat dict rather
    than nesting it under trim like the availability matrix."""
    for page in pdf.pages:
        text = page.extract_text() or ""
        lines_of_text = text.splitlines()
        if len(lines_of_text) < 2 or lines_of_text[1].strip() != _SECTION_TITLE:
            continue

        lines = group_into_lines(page.extract_words())

        column_x: list[float] | None = None
        data_rows: list[tuple[list[dict], list[dict], list[dict]]] = []
        for line in lines:
            split = _split_row(line)
            if split is None:
                continue
            name_tokens, avail_tokens, price_tokens = split
            if column_x is None:
                column_x = [t["x0"] for t in avail_tokens]
            if len(avail_tokens) != len(column_x):
                continue  # incomplete/untrustworthy row, better to skip it
            data_rows.append((name_tokens, avail_tokens, price_tokens))

        if column_x is None:
            return {}, {}

        raw_labels = group_rotated_chars_into_columns(page.chars)
        trims = _assign_column_labels(raw_labels, column_x)

        result: dict[str, dict[str, str]] = {trim: {} for trim in trims}
        prices: dict[str, float] = {}
        for name_tokens, avail_tokens, price_tokens in data_rows:
            item_name = " ".join(t["text"] for t in name_tokens).strip()
            if not item_name:
                continue  # the name wrapped onto another line, see docstring
            price = _parse_price(price_tokens)
            if price is not None:
                prices[item_name] = price
            for trim, token in zip(trims, avail_tokens, strict=False):
                if token["text"] == _AVAILABLE:
                    result[trim][item_name] = "OPTIONAL"

        return result, prices

    return {}, {}

"""Extracts equipment from Peugeot's own "VÝBAVA <MODEL>" pages (verified
word-by-word via `page.extract_words()` against peugeot_208_cenik.pdf,
cross-checked against peugeot_2008_cenik.pdf/peugeot_3008_cenik.pdf) - a
checkbox matrix, one column per trim, with two things `skoda_equipment.py`
doesn't need to handle: a genuinely mixed mark alphabet per cell (a plain
availability glyph OR a real per-trim price), and marks that sit on their
own physical text line, detached from the item name they belong to.

**The "included" glyph is Private-Use-Area** `""` (a Wingdings-style
icon-font bullet - confirmed via `ord()` on `page.extract_words()` output;
`extract_text()` renders it as nothing, not even a replacement character,
which is why every earlier look at this page via `extract_text()` alone
found no visible checkbox at all). "–" (plain en dash) means unavailable.
Some rows are a HYBRID: one or more trim cells hold a real price (e.g.
"10 000 Kč") instead of either mark - a genuinely `OPTIONAL` item with a
disclosed per-trim surcharge, not "everything non-included is
unavailable". A handful of cells are a compound "– /  (1)"
(conditional on another option, per a footnote) - not read at all,
same "skip rather than guess" precedent as everywhere else in this
codebase, since which side of the "/" applies isn't stated anywhere on
the page itself.

**Column anchors are derived from the data, not the header row.** The 5
trim names print at one x0 set (e.g. 356/398/439/490/545 on the 208's own
page) and the mark/price cells at a DIFFERENT, page-specific x0 set
(e.g. 366/412/457/503/548) - close but never identical, so matching is by
nearest x0 (`_nearest_index`), the same principle `skoda_equipment.py`'s
`_assign_column_labels` uses for its own rotated header. The column count
itself is read off the first row whose mark-region clusters into exactly
`len(trims)` groups, then reused for the rest of the page - trims (and
their left-to-right order) come from `PeugeotParser`'s own already-
extracted variants for this model, the same "reuse the price table's own
trim discovery" trick `mazda_equipment.py`/`mg_equipment.py` use, since a
model-code column (e.g. "UF01", "NF15") sits in its own narrow x0 band
between the item name and the marks and could otherwise be mistaken for
one - it's simply outside the x0 window this module reads as marks
(`_MARK_MIN_X0`), so it's never captured (not a loss: nothing downstream
needs it).

**Marks sit on their own row, detached from the item's name.** A row like

    ABS + EBA + EBD + Automatická aktivace výstražných světel v případě
                                                    ● ● ● ● ●   (own line)
    prudkého brzdění

has its 5 marks on a physical line BETWEEN the name's own two wrapped
lines - not appended to either one (verified: this shape recurs for every
multi-line item on the page, always with the marks line landing somewhere
inside the name's own line span, never reliably first or last). Since
there's no bullet or dash prefix (unlike Dacia's/CUPRA's own wrapped
items) to tell a continuation line from a new item's own first line, item
boundaries are found from the NAME lines' own vertical spacing instead:
consecutive name-only lines less than `_CONTINUATION_GAP_MAX` apart
belong to the same item (a wrapped paragraph); a bigger gap starts a new
item (verified: within-item gaps are ~3-8pt here, one item to the next is
~20pt+ - the two never overlap on this page). Each mark-row is then
assigned to whichever item paragraph has the LATEST start that's still at
or before the mark-row's own top - correctly leaves a paragraph with no
marks-row at all (e.g. 208's own "Airbag řidiče a spolujezdce s možností
deaktivace", which the source simply never gives per-trim availability
for) unassigned rather than guessing, since the next real marks-row
belongs to the FOLLOWING paragraph instead (its own start-top is closer
to that marks-row's top without going past it).

Only ONE section per page is handled - Rifter's own multi-sub-table
equipment pages (see PeugeotParser's module docstring for its price
table's own multi-section shape) are out of scope for the same reason
VW's "Příplatková výbava" and Kia's own availability matrix are - a
materially different, harder parsing problem layered on top of what was
needed just to stop equipment being entirely absent."""
from __future__ import annotations

import re

import pdfplumber

_INCLUDED_MARK = ""
_UNAVAILABLE_MARK = "–"
_NAME_MAX_X0 = 310.0
_MARK_MIN_X0 = 350.0
_MARK_COLUMN_GAP = 15.0  # pt; gap between two cells' own x0 clusters on one mark-row
_MARK_ROW_GAP = 3.0  # pt; a mark-row's own tokens land within this of each other
_CONTINUATION_GAP_MAX = 12.0  # pt; within-item wrapped-line gap vs. ~20pt+ between items
_PRICE_TOKEN_RE = re.compile(r"^[\d ]+$")


def _is_header_line(words: list[dict]) -> bool:
    text = " ".join(w["text"].upper() for w in words)
    return text.startswith("VÝBAVA ")


def _cluster_by_gap(words: list[dict], gap: float) -> list[list[dict]]:
    words = sorted(words, key=lambda w: w["x0"])
    clusters: list[list[dict]] = [[words[0]]]
    for word in words[1:]:
        if word["x0"] - clusters[-1][-1]["x1"] > gap:
            clusters.append([word])
        else:
            clusters[-1].append(word)
    return clusters


def _cluster_rows_by_top(words: list[dict], gap: float) -> list[list[dict]]:
    words = sorted(words, key=lambda w: w["top"])
    rows: list[list[dict]] = [[words[0]]]
    for word in words[1:]:
        if word["top"] - rows[-1][-1]["top"] > gap:
            rows.append([word])
        else:
            rows[-1].append(word)
    return rows


def _cell_value(cluster: list[dict]) -> tuple[str, float | None] | None:
    """Args:
        cluster: One mark-row's words belonging to a single trim column.

    Returns:
        `("STANDARD", None)`, `("UNAVAILABLE", None)`, `("OPTIONAL",
        price)`, or `None` if the cluster isn't cleanly one of those (a
        compound "– /  (1)"-style conditional cell, or anything
        else unrecognized) - never guessed at.
    """
    texts = [w["text"] for w in cluster]
    if texts == [_INCLUDED_MARK]:
        return "STANDARD", None
    if texts == [_UNAVAILABLE_MARK] or texts == ["-"]:
        return "UNAVAILABLE", None
    if texts and texts[-1] == "Kč" and all(_PRICE_TOKEN_RE.match(t) for t in texts[:-1]):
        digits = "".join(texts[:-1]).replace(" ", "")
        if digits.isdigit():
            return "OPTIONAL", float(digits)
    return None


def _nearest_index(x0: float, anchors: list[float]) -> int:
    return min(range(len(anchors)), key=lambda i: abs(anchors[i] - x0))


def _find_column_anchors(mark_rows: list[list[dict]], column_count: int) -> list[float] | None:
    """Args:
        mark_rows: Every mark-region row on the page (see
            `_cluster_rows_by_top`), each already `x0`-sorted.
        column_count: `len(trims)` for this model.

    Returns:
        The first row's own cluster x0s that clusters into exactly
        `column_count` groups (sorted left to right), reused as this
        page's column anchors - or `None` if no such row exists.
    """
    for row in mark_rows:
        clusters = _cluster_by_gap(row, _MARK_COLUMN_GAP)
        if len(clusters) == column_count:
            return [c[0]["x0"] for c in clusters]
    return None


def _group_paragraphs(name_lines: list[tuple[float, list[dict]]]) -> list[tuple[float, float, str]]:
    """Args:
        name_lines: `(top, words)` for every name-column line on the page,
            sorted by `top`.

    Returns:
        `(start_top, end_top, text)` per item paragraph - consecutive
        lines less than `_CONTINUATION_GAP_MAX` apart merge into one (see
        module docstring).
    """
    paragraphs: list[list[tuple[float, list[dict]]]] = []
    for top, words in name_lines:
        if paragraphs and top - paragraphs[-1][-1][0] <= _CONTINUATION_GAP_MAX:
            paragraphs[-1].append((top, words))
        else:
            paragraphs.append([(top, words)])

    result = []
    for para in paragraphs:
        text = " ".join(w["text"] for _, words in para for w in words).strip()
        result.append((para[0][0], para[-1][0], text))
    return result


def parse_equipment(
    pdf: pdfplumber.PDF, trims_by_model: dict[str, list[str]]
) -> dict[str, dict[str, tuple[dict[str, str], dict[str, float]]]]:
    """Args:
        pdf: The opened Peugeot price-list PDF.
        trims_by_model: Every model this document covers, mapped to its
            own trim names in the exact left-to-right order and casing
            `PeugeotParser` already produces for `ExtractedVariant.trim`.

    Returns:
        `{model: {trim: (equipment, equipment_surcharge)}}` - `equipment`
        maps item name to `"STANDARD"`/`"OPTIONAL"`, `equipment_surcharge`
        holds the price (in CZK) for each `"OPTIONAL"` item on that trim.
        A model/page this module can't confidently parse (no page found,
        ambiguous column count, Rifter's multi-section shape, ...) is
        simply absent from the result rather than guessed at.
    """
    result: dict[str, dict[str, tuple[dict[str, str], dict[str, float]]]] = {}

    for page in pdf.pages:
        all_words = page.extract_words()
        if not all_words or not _is_header_line(all_words[:3]):
            continue
        model = next((m for m in trims_by_model if m.upper() in " ".join(w["text"] for w in all_words[:6]).upper()), None)
        if model is None:
            continue
        trims = trims_by_model[model]

        name_words = [w for w in all_words if w["x0"] < _NAME_MAX_X0]
        mark_words = [w for w in all_words if w["x0"] >= _MARK_MIN_X0]
        # Drop the trim-header line itself (top ~88 on every fixture seen,
        # well above the first real row) from the mark-region words so it
        # never gets mistaken for a data row.
        mark_words = [w for w in mark_words if w["top"] > 100]
        if not name_words or not mark_words:
            continue

        mark_rows = _cluster_rows_by_top(mark_words, _MARK_ROW_GAP)
        anchors = _find_column_anchors(mark_rows, len(trims))
        if anchors is None:
            continue

        name_lines_by_top: dict[float, list[dict]] = {}
        for w in name_words:
            name_lines_by_top.setdefault(round(w["top"], 1), []).append(w)
        name_lines = sorted(
            ((top, sorted(ws, key=lambda w: w["x0"])) for top, ws in name_lines_by_top.items()),
            key=lambda item: item[0],
        )
        paragraphs = _group_paragraphs(name_lines)
        if not paragraphs:
            continue

        model_equipment = result.setdefault(model, {t: ({}, {}) for t in trims})

        for row in mark_rows:
            row_top = row[0]["top"]
            owner = max(
                (p for p in paragraphs if p[0] <= row_top),
                key=lambda p: p[0],
                default=None,
            )
            if owner is None or not owner[2]:
                continue
            item_name = owner[2]

            clusters = _cluster_by_gap(row, _MARK_COLUMN_GAP)
            if len(clusters) != len(trims):
                continue
            for cluster in clusters:
                trim_index = _nearest_index(cluster[0]["x0"], anchors)
                trim = trims[trim_index]
                cell = _cell_value(cluster)
                if cell is None:
                    continue
                status, price = cell
                equipment, surcharge = model_equipment[trim]
                if status == "STANDARD":
                    equipment[item_name] = "STANDARD"
                    # An identical item_name can legitimately recur under a
                    # different row elsewhere on the page (e.g. a paint
                    # option repeated per engine block) - if an earlier
                    # pass already recorded a price for this same name on
                    # this trim, drop it so `equipment`/`equipment_surcharge`
                    # never disagree (STANDARD must never carry a price -
                    # see option_availability's own CHECK constraint).
                    surcharge.pop(item_name, None)
                elif status == "OPTIONAL" and price is not None:
                    equipment[item_name] = "OPTIONAL"
                    surcharge[item_name] = price

    return result

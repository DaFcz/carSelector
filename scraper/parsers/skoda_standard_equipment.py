"""Extracts standard equipment from the per-trim "Standardní výbava" pages
of a Škoda price list - one page per trim level, same layout for combustion
models (`skoda_ice.py`) and EVs (`skoda_ev.py`):

    Selection                                       <- trim title (large, bold)
    (navíc oproti výbavovému stupni Essence)        <- "in addition to trim X"
    Design          Bezpečnost        Funkčnost     <- section headings (bold)
    Kola z lehké…   LED přední…       Startování…   <- items (light), up to 4
    - disk 8J × 19" …                               <- columns side by side

Items are plain text, not a table - so, like the price table, they're
rebuilt from word positions:

1. Only words at the page's body font size count; the navigation bar, the
   trim title and superscript footnote marks ("Digitální klíč¹") are a
   different size. The footnote text at the bottom IS body size, so
   everything from the first line starting with a small footnote number
   ("¹ Mobilní digitální klíč je…") down is dropped.
2. Words are assigned to a column by x-position. Column starts are the
   section headings' x0 values (Design/Bezpečnost/Funkčnost) plus any x0
   where item lines start on several different lines - the headings alone
   aren't enough, a long section can spill into a fourth column (Elroq's
   "Infotainment"), and repetition alone isn't either, a column can hold a
   single item (Octavia Sportline's "Bezpečnost").
3. Bold body-size words are section headings (Design/Komfort/Asistovaná
   jízda, ...) - not items, but they do end the previous item.
4. Within a column, a line continues the previous item when it follows
   closely below it and either starts lowercase/with "-"/"(" (a wrapped
   phrase, or a detail line such as "- disk 8J × 19" ET45…") or the
   previous line ends with "," or "-" ("…Škoda Connect Standard -" /
   "Proaktivní servis, …"); otherwise it's a new item.
5. "•" lines are sub-items of the light (not bold) group label right above
   them ("Asistovaná jízda" / "• Travel Assist 3.0" / "• Nouzový asistent").
   The sub-items are kept as items, without the "•"; the label is dropped.

A trim page lists only what it adds on top of its base trim ("navíc oproti
výbavovému stupni X"), so each trim's result is its base's (recursively)
plus its own. The price list itself says "in addition to", so an upgraded
item (e.g. 19" wheels -> 20" wheels) appears in both - it's not guessed
which item the new one replaces.

Known gap: a page describing TWO trims side by side (Octavia's "Standardní
výbava Classic / Standardní výbava Dynamic" promo models) is skipped -
those trims get no standard equipment rather than a wrong mix.
"""

from __future__ import annotations

import re
from collections import Counter

import pdfplumber

from ._pdf_layout import group_into_lines
from .skoda_equipment import parse_standalone_equipment

_BASE_TRIM_RE = re.compile(r"^\(navíc oproti výbavovému stupni (.+)\)$")
_SECTION_HEADINGS = ("Design", "Bezpečnost", "Funkčnost", "Komfort")
_COLUMN_START_TOLERANCE = 6.0
# A wrapped line sits ~18pt under its first line at 15pt body text, a new
# item ~30pt - so anything under 1.5× the font size counts as "close".
_CONTINUATION_GAP_FACTOR = 1.5


def _is_bold(word: dict) -> bool:
    return "bold" in word["fontname"].lower()


def _body_size(words: list[dict]) -> float:
    """The most common (rounded) font size on the page - the item text."""
    return Counter(round(w["size"], 1) for w in words).most_common(1)[0][0]


def _footnote_top(words: list[dict], body: float) -> float:
    """`top` of the first footnote line (a smaller-than-body number that
    starts its line, as opposed to an inline superscript mark after a
    word), or infinity if the page has none."""
    tops = [
        w["top"]
        for w in words
        if w["size"] < body - 0.5
        and w["text"].isdigit()
        and not any(o is not w and abs(o["top"] - w["top"]) < 3 and o["x1"] <= w["x0"] + 1 for o in words)
    ]
    return min(tops, default=float("inf"))


def _column_starts(lines: list[list[dict]], heading_x: list[float]) -> list[float]:
    """`heading_x` plus x0 values where a run of words starts on at least
    two lines (see module docstring, step 2), sorted, near-duplicates merged."""
    starts: list[float] = []
    for line in lines:
        previous_x1: float | None = None
        for word in line:
            if previous_x1 is None or word["x0"] - previous_x1 > 3 * word["size"]:
                starts.append(word["x0"])
            previous_x1 = word["x1"]

    counts = Counter(round(x) for x in starts)
    candidates = {x for x, n in counts.items() if n >= 2} | {round(x) for x in heading_x}
    merged: list[float] = []
    for x in sorted(candidates):
        if not merged or x - merged[-1] > _COLUMN_START_TOLERANCE:
            merged.append(float(x))
    return merged


def _column_for(x0: float, starts: list[float]) -> int:
    """Index of the last column starting at or before `x0`."""
    column = 0
    for index, start in enumerate(starts):
        if x0 >= start - _COLUMN_START_TOLERANCE:
            column = index
    return column


def _parse_trim_page(page: pdfplumber.page.Page) -> tuple[str, str | None, list[str]] | None:
    """Returns `(trim, base_trim_or_None, items)` if `page` is a single-trim
    standard-equipment page, else None."""
    text_lines = (page.extract_text() or "").splitlines()
    if len(text_lines) < 3:
        return None
    trim = text_lines[1].strip()
    base_match = _BASE_TRIM_RE.match(text_lines[2].strip())
    headings_line = text_lines[3] if base_match else text_lines[2]
    if not any(heading in headings_line.split() for heading in _SECTION_HEADINGS):
        return None
    if trim.startswith("Standardní výbava"):
        return None  # two trims on one page, see module docstring

    words = page.extract_words(extra_attrs=["fontname", "size"])
    body = _body_size(words)
    footnote_top = _footnote_top(words, body)
    body_words = [w for w in words if abs(w["size"] - body) < 0.5 and w["top"] < footnote_top - 2]
    lines = group_into_lines(body_words)
    # Everything above (and including) the section-heading row is title/intro.
    heading_line = next(
        (line for line in lines if any(w["text"] in _SECTION_HEADINGS and _is_bold(w) for w in line)),
        None,
    )
    if heading_line is None:
        return None
    heading_top = heading_line[0]["top"]
    heading_x = [w["x0"] for w in heading_line if w["text"] in _SECTION_HEADINGS]
    lines = [line for line in lines if line[0]["top"] > heading_top + 1]
    starts = _column_starts(lines, heading_x)
    if not starts:
        return None

    # (top, text, is_heading) per column, in reading order.
    columns: dict[int, list[tuple[float, str, bool]]] = {}
    for line in lines:
        runs: dict[int, list[dict]] = {}
        for word in line:
            runs.setdefault(_column_for(word["x0"], starts), []).append(word)
        for column, run in runs.items():
            text = " ".join(w["text"] for w in run).strip()
            columns.setdefault(column, []).append((run[0]["top"], text, all(_is_bold(w) for w in run)))

    items: list[str] = []
    for column in sorted(columns):
        # [text, is_bullet, top of first line] per item, in order
        column_items: list[list] = []
        current: list | None = None
        current_bottom = 0.0
        for top, text, is_heading in columns[column]:
            if is_heading:
                current = None
                continue
            is_bullet = text.startswith("•")
            text = text.lstrip("•").strip()
            is_continuation = (
                current is not None
                and not is_bullet
                and top - current_bottom < body * _CONTINUATION_GAP_FACTOR
                and (text[:1].islower() or text[:1] in "-(" or current[0].endswith((",", "-")))
            )
            if is_continuation:
                current[0] = f"{current[0]} {text}"
            else:
                current = [text, is_bullet, top]
                column_items.append(current)
            current_bottom = top
        for index, (text, is_bullet, _top) in enumerate(column_items):
            next_is_bullet = index + 1 < len(column_items) and column_items[index + 1][1]
            if not is_bullet and next_is_bullet:
                continue  # group label, see module docstring step 5
            items.append(text)

    return trim, base_match.group(1).strip() if base_match else None, items


def parse_standard_equipment(pdf: pdfplumber.PDF) -> dict[str, dict[str, str]]:
    """Returns `{trim_level: {item_name: "STANDARD"}}` with each trim's base
    trim's items included (see module docstring). Empty if the price list
    has no standard-equipment pages in this layout."""
    own: dict[str, list[str]] = {}
    base_of: dict[str, str | None] = {}
    for page in pdf.pages:
        parsed = _parse_trim_page(page)
        if parsed is None:
            continue
        trim, base, items = parsed
        own[trim] = items
        base_of[trim] = base

    def resolve(trim: str, seen: frozenset[str] = frozenset()) -> list[str]:
        if trim in seen or trim not in own:
            return []
        base = base_of[trim]
        inherited = resolve(base, seen | {trim}) if base else []
        return [*inherited, *own[trim]]

    return {trim: {item: "STANDARD" for item in resolve(trim)} for trim in own}


def parse_equipment(pdf: pdfplumber.PDF) -> tuple[dict[str, dict[str, str]], dict[str, float]]:
    """Standard equipment (this module) and paid standalone items
    (`skoda_equipment.parse_standalone_equipment`) of one price list,
    merged per trim - what `skoda_ice`/`skoda_ev` attach to each variant.

    Returns:
        `({trim: {item_name: "STANDARD" | "OPTIONAL"}}, {item_name: price_czk})`.
        An item that's both standard on a trim and listed as a paid item
        for it stays `STANDARD` (e.g. Elroq L&K's heat pump).
    """
    optional, prices = parse_standalone_equipment(pdf)
    standard = parse_standard_equipment(pdf)
    merged = {trim: {**optional.get(trim, {}), **standard.get(trim, {})} for trim in {*optional, *standard}}
    return merged, prices


def equipment_for_trim(equipment_by_trim: dict[str, dict[str, str]], trim: str) -> dict[str, str]:
    """Looks up `trim`'s equipment, tolerating the price table's shorter
    trim name: Epiq's/Peaq's price tables read "First"/"Exclusive" where the
    equipment pages say "First Edition"/"Exclusive Selection". Falls back to
    the ONE equipment trim starting with `trim` + " " - if several do, it's
    ambiguous and nothing is returned rather than a guess."""
    if trim in equipment_by_trim:
        return equipment_by_trim[trim]
    candidates = [name for name in equipment_by_trim if name.startswith(f"{trim} ")]
    return equipment_by_trim[candidates[0]] if len(candidates) == 1 else {}

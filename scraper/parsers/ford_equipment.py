"""Extracts standard equipment from Ford's own "PŘEHLED VÝBAVOVÝCH STUPŇŮ"/
"PŘEHLED STUPŇŮ VÝBAVY" ("Trim levels overview") page(s) - verified against
all four fixtures (ford_bronco_cenik.pdf, ford_kuga_cenik.pdf,
ford_mustang_cenik.pdf, ford_puma_cenik.pdf). Like `dacia_equipment.py`,
this is an unstructured bullet list per trim with no prices anywhere on
this page, so every listed item is simply `STANDARD` and
`ExtractedVariant.equipment_surcharge` is never populated here.

Every model's overview page(s) use the same delta convention as Dacia's
"navíc oproti <trim>" - a trim section lists only what it adds ON TOP OF
an explicitly named other trim - but Ford's own fixtures use THREE
different phrasings for that reference, verified against real text (grep
for "oproti"/"Hlavní prvky" across all four fixtures found exactly these,
nothing else):
- Bronco/Kuga: inline, in parentheses right after the trim name on the
  SAME line, e.g. "BADLANDS (navíc oproti Outer Banks)",
  "ST-Line X (navíc oproti ST-Line)".
- Mustang: on its own following line, no parentheses, no colon -
  "Odlišnosti oproti verzi GT".
- Puma: on its own following line, colon-terminated - "Navíc oproti
  výbavě Titanium:" - and its own FIRST trim's section is marked instead
  by "Hlavní prvky standardní výbavy:" (no reference - the same "base
  vs. delta" marker text Dacia's price lists use, just "standardní"
  instead of "sériové").

Critically, the base a trim's delta is measured against is NOT always the
immediately preceding section (unlike Dacia, which is always linear) -
Kuga's own "Top Edition", "ST-Line" AND "Active X" are all three "navíc
oproti Titanium" (not chained to each other), while "ST-Line X" is "navíc
oproti ST-Line" and "BlueCruise Edition" is "navíc oproti ST-Line X".
`_KNOWN_TRIMS` (the fixed, verified set of trim headings across all four
models - no name collides across models) lets `_OverviewState` resolve
the NAMED reference directly out of its own `trim_items` (already-finalized
sections), rather than assuming a chain.

**Every one of the four overview pages is a two-column bullet layout**
(verified via `page.extract_words()` coordinates: bullet markers cluster
at x0≈257 for the left column and x0≈416-424 for the right one, a ~150pt
gap dwarfing the sub-2pt jitter within either column) - `extract_text()`
alone interleaves the two columns' words left-to-right per physical PDF
row, which would silently splice an unrelated left-column item and
right-column item into one garbled "bullet". `_column_threshold` derives
the split point per page from the bullet markers' own x0 clustering
(same gap-clustering principle `ford.py`'s own `_cluster_by_gap` uses for
its header, just applied to two columns instead of N trim columns)
rather than hardcoding a pixel value, since nothing in this codebase's
conventions assumes a fixed page geometry. Every trim heading and
reference-marker line was verified to sit entirely in the LEFT column's
x-range (the right column is blank on those rows - the two-column bullet
grid only starts filling in on the row below), so only the left cell of
each row is checked for headings/markers; the right cell only ever
carries bullet-item text.

A trim's own overview section can span more than one page with no
repeated title (Kuga: Titanium/Top Edition/ST-Line/ST-Line X on page 4,
Active X/BlueCruise Edition continue directly at the top of page 5 with
no new "PŘEHLED..." heading; Puma similarly carries BlueCruise Edition
onto page 5) - `_collect_section_rows` treats the whole document as one
continuous row stream from the first "PŘEHLED..." title through to
whichever of `_END_MARKERS` appears first ("STANDARDNÍ VÝBAVA A VÝBAVA NA
PŘÁNÍ" - Ford's own real availability-and-price matrix immediately below
the overview on Bronco/Kuga/Puma; "SPECIÁLNÍ EDICE"/"SPECIÁLNÍ SÉRIE" - a
marketing page immediately after Mustang's overview, which has no matrix
section at all), so a document's own page boundaries never need to be
special-cased.

That matrix section (a real STANDARD/optional-with-price availability
grid, legend "A standardní výbava, — nelze objednat, S lze objednat jako
součást zvýhodněné sady či jiné výbavy") is NOT parsed here - a
Škoda/Mazda-style column-per-trim matrix with per-cell prices spanning
several differently-titled category pages (BEZPEČNOST/FUNKČNÍ VÝBAVA/
INTERIÉR/EXTERIÉR/SADY VÝBAVY NA PŘÁNÍ/...), a materially bigger vertical
slice than this module's - a known, documented gap for a follow-up, same
"scope, don't silently mis-parse" precedent as `ford.py`'s own module
docstring's "Scope" section for the models this parser doesn't cover at
all.
"""
from __future__ import annotations

import re

import pdfplumber

from ._pdf_layout import group_into_lines, line_text

_BULLET = "·"
_START_MARKERS = ("PŘEHLED VÝBAVOVÝCH STUPŇŮ", "PŘEHLED STUPŇŮ VÝBAVY")
_END_MARKERS = ("STANDARDNÍ VÝBAVA A VÝBAVA NA PŘÁNÍ", "SPECIÁLNÍ EDICE", "SPECIÁLNÍ SÉRIE")
_SKIP_PREFIXES = ("Obrázky",)
_COLUMN_GAP_THRESHOLD = 50.0  # pt; the two columns' bullets are ~150pt+ apart, same-column jitter is <1pt

_BASE_MARKER_RE = re.compile(r"hlavní prvky (?:standardní|sériové) výbavy", re.IGNORECASE)
_REF_RE = re.compile(
    r"(?:navíc oproti(?: výbavě)?|odlišnosti oproti verzi)\s+([^:()]+)",
    re.IGNORECASE,
)

# Every trim heading verified across all four fixtures (see module docstring's
# grep of "oproti"/"Hlavní prvky") - no name collides across models, so one
# flat dict covers all of them, same precedent as dacia_equipment._KNOWN_TRIMS.
_KNOWN_TRIMS = {
    "OUTER BANKS": "Outer Banks",
    "BADLANDS": "Badlands",
    "TITANIUM": "Titanium",
    "TOP EDITION": "Top Edition",
    "ST-LINE": "ST-Line",
    "ST-LINE X": "ST-Line X",
    "ACTIVE X": "Active X",
    "BLUECRUISE EDITION": "BlueCruise Edition",
    "GT": "GT",
    "DARK HORSE": "Dark Horse",
}


def _strip_parenthetical(text: str) -> tuple[str, str | None]:
    """Args:
        text: One row's left-cell text (see module docstring - headings
            and reference markers only ever appear there).

    Returns:
        `(head, inner)` - `head` is `text` with a trailing "(...)"
        removed (e.g. "BADLANDS (navíc oproti Outer Banks)" ->
        "BADLANDS"); `inner` is that parenthetical's own content
        (e.g. "navíc oproti Outer Banks"), or `None` if `text` has no
        "(" at all.
    """
    open_idx = text.find("(")
    if open_idx == -1:
        return text.strip(), None
    close_idx = text.find(")", open_idx)
    inner = text[open_idx + 1 : close_idx] if close_idx != -1 else text[open_idx + 1 :]
    return text[:open_idx].strip(), inner.strip()


def _column_threshold(lines: list[list[dict]]) -> float:
    """Args:
        lines: One page's lines (see `_pdf_layout.group_into_lines`).

    Returns:
        The x-coordinate splitting the left/right bullet columns (the
        midpoint between the two clusters of bullet-marker x0s - see
        module docstring), or `float("inf")` (put everything in the left
        cell) if this page's bullets don't cluster into exactly two
        groups - a page with no two-column layout to split.
    """
    xs = sorted({w["x0"] for line in lines for w in line if w["text"].startswith(_BULLET)})
    if len(xs) < 2:
        return float("inf")
    clusters: list[list[float]] = [[xs[0]]]
    for x in xs[1:]:
        if x - clusters[-1][-1] > _COLUMN_GAP_THRESHOLD:
            clusters.append([x])
        else:
            clusters[-1].append(x)
    if len(clusters) != 2:
        return float("inf")
    return (clusters[0][-1] + clusters[1][0]) / 2


def _split_columns(line: list[dict], threshold: float) -> tuple[list[dict], list[dict]]:
    """Args:
        line: One row's words, left to right.
        threshold: This page's left/right split x-coordinate (see `_column_threshold`).

    Returns:
        `(left_words, right_words)` - `line` partitioned by `x0` against `threshold`.
    """
    return [w for w in line if w["x0"] < threshold], [w for w in line if w["x0"] >= threshold]


class _OverviewState:
    """Accumulates `{trim: {item_name: "STANDARD"}}` across a document's
    whole overview section, one two-column row at a time. Item text for
    the left and right bullet columns is buffered separately
    (`_left_buffer`/`_right_buffer`, since the two columns' bullets
    interleave independently down the page - see module docstring), but
    both feed the SAME `_accumulated` set for whichever trim is
    currently open, since a heading always spans the full row (verified
    to sit in the left column only, but ends both columns' current
    items - see module docstring)."""

    def __init__(self) -> None:
        self.trim_items: dict[str, dict[str, str]] = {}
        self._accumulated: dict[str, str] = {}
        self._current_trim: str | None = None
        self._left_buffer: list[str] = []
        self._right_buffer: list[str] = []

    def _flush(self, buffer: list[str]) -> None:
        name = " ".join(buffer).strip()
        if name and self._current_trim is not None:
            self._accumulated[name] = "STANDARD"
        buffer.clear()

    def _flush_both(self) -> None:
        self._flush(self._left_buffer)
        self._flush(self._right_buffer)

    def _save_current_trim(self) -> None:
        if self._current_trim is not None:
            self.trim_items[self._current_trim] = dict(self._accumulated)

    def _resolve_reference(self, reference: str | None) -> dict[str, str]:
        """Args:
            reference: The raw referenced-trim text captured by `_REF_RE`
                (e.g. "Outer Banks", "ST-Line"), or `None` for a trim with
                no delta reference (this section's own base).

        Returns:
            A copy of the referenced trim's own already-finalized
            equipment set (from `self.trim_items`, saved by
            `_save_current_trim` when that trim's own section ended), or
            `{}` if there's no reference or it doesn't resolve to a known
            trim (not fabricated - see module docstring's
            `_KNOWN_TRIMS`).
        """
        if reference is None:
            return {}
        ref_trim = _KNOWN_TRIMS.get(reference.strip().upper())
        return dict(self.trim_items.get(ref_trim, {})) if ref_trim else {}

    def _start_trim(self, canonical: str, reference: str | None) -> None:
        self._flush_both()
        self._save_current_trim()
        self._current_trim = canonical
        self._accumulated = self._resolve_reference(reference)

    def handle_left(self, text: str) -> None:
        """Args:
            text: This row's left-cell text - may be a trim heading (bare,
                or with an inline "(navíc oproti ...)" reference), a
                standalone reference/base marker line, a bullet item, a
                wrapped bullet continuation, or the page footer disclaimer.
        """
        if not text or text.startswith(_SKIP_PREFIXES):
            return

        head, parenthetical = _strip_parenthetical(text)
        canonical = _KNOWN_TRIMS.get(head.upper())
        if canonical is not None:
            reference = None
            if parenthetical:
                ref_match = _REF_RE.search(parenthetical)
                reference = ref_match.group(1) if ref_match else None
            self._start_trim(canonical, reference)
            return

        if _BASE_MARKER_RE.search(text):
            self._flush_both()
            return

        ref_match = _REF_RE.search(text)
        if ref_match and self._current_trim is not None:
            self._flush_both()
            self._accumulated = self._resolve_reference(ref_match.group(1))
            return

        self._handle_item_text(text, self._left_buffer)

    def handle_right(self, text: str) -> None:
        """Args:
            text: This row's right-cell text - always either a bullet
                item, a wrapped continuation, or the page footer (headings
                and reference markers only ever appear in the left cell -
                see module docstring)."""
        if not text or text.startswith(_SKIP_PREFIXES):
            return
        self._handle_item_text(text, self._right_buffer)

    def _handle_item_text(self, text: str, buffer: list[str]) -> None:
        if text.startswith(_BULLET):
            self._flush(buffer)
            rest = text[len(_BULLET) :].strip()
            if rest:
                buffer.append(rest)
            return
        if self._current_trim is not None:
            buffer.append(text)

    def finish(self) -> dict[str, dict[str, str]]:
        """Returns:
            `self.trim_items`, after flushing and saving whatever trim was
            still open when the row stream ended."""
        self._flush_both()
        self._save_current_trim()
        return self.trim_items


def _collect_section_rows(pdf: pdfplumber.PDF) -> list[tuple[list[dict], list[dict]]]:
    """Args:
        pdf: The opened Ford price-list PDF.

    Returns:
        `(left_words, right_words)` per row (see `_split_columns`), for
        every row between the first `_START_MARKERS` title and whichever
        `_END_MARKERS` line comes first - possibly spanning more than one
        page with no repeated title (see module docstring) - `[]` if no
        start marker is found anywhere in the document.
    """
    rows: list[tuple[list[dict], list[dict]]] = []
    collecting = False

    for page in pdf.pages:
        lines = group_into_lines(page.extract_words())
        threshold = _column_threshold(lines)

        for line in lines:
            text = line_text(line)
            upper = text.upper()
            if not collecting:
                if any(marker in upper for marker in _START_MARKERS):
                    collecting = True
                continue
            if any(marker in upper for marker in _END_MARKERS):
                return rows
            rows.append(_split_columns(line, threshold))

    return rows


def parse_standard_equipment(pdf: pdfplumber.PDF) -> dict[str, dict[str, str]]:
    """Args:
        pdf: The opened Ford price-list PDF.

    Returns:
        `{trim: {item_name: "STANDARD"}}`, keyed by the exact trim-heading
        text from the "PŘEHLED VÝBAVOVÝCH STUPŇŮ"/"PŘEHLED STUPŇŮ VÝBAVY"
        overview page(s) (see `_KNOWN_TRIMS`) - each trim's dict already
        resolved to its own full standard equipment (deltas folded in, see
        module docstring). `{}` if the page isn't found.
    """
    state = _OverviewState()
    for left, right in _collect_section_rows(pdf):
        state.handle_left(line_text(left))
        state.handle_right(line_text(right))
    return state.finish()

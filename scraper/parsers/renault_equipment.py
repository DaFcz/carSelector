"""Extracts standard equipment from Renault price lists' own "hlavní prvky
sériové výbavy" bullet-list page (page 3 in all twelve fixtures, page 3+4
only for the Renault 4/Renault 5 documents - see below) - the same per-trim
overview format Dacia's own price lists use (`dacia_equipment.py`), right
down to the "navíc oproti <trim>" delta convention distinguishing whether a
trim's section restates its whole standard-equipment list or only what it
adds over a lower trim's own list.

Verified against all twelve fixtures (scraper/tests/fixtures/renault_*
_cenik.pdf). Seven of them - Arkana, Captur, Clio, Espace, Rafale, Scenic,
Twingo - lay this page out as a single column, one "• <item>" bullet per
physical line (occasionally wrapping onto a following line with no bullet
of its own; Clio's own PDF even puts the "•" alone on its own line, with the
item text starting only on the next line - verified via its own page 3 -
which the state machine below handles for free, since an item's name is
just whatever non-bullet text accumulates between two bullet markers,
whether that's zero or several lines). This is the same physical row shape
`dacia_equipment.py`'s own `_parse_equipment_text` already handles, reused
here with one difference: the trim heading for a section is found by
POSITION (the line immediately above its own "hlavní prvky sériové
výbavy..." marker - verified true in every one of the seven fixtures',
Captur example: "...EVOLUTION\nhlavní prvky sériové výbavy:...TECHNO\nhlavní
prvky sériové výbavy navíc oproti Evolution:...") rather than against a
fixed `_KNOWN_TRIMS` lookup table - Renault's current lineup spans far more
distinct trim names across its twelve models ("Evolution"/"Techno"/"Esprit
Alpine"/"Iconic"/"Atelier Alpine"/"Roland-Garros"/"Cinq"/"Plein Sud"/...)
than Dacia's four, so hardcoding them all would be far more brittle than
reading the one line that's always, structurally, right there. Whatever
casing the source PDF uses (`.title()`-normalized the same way
`renault.py`'s own price-table trim headings are, for the same smallcaps-
style-font reason documented there) becomes the dict key, which is also
exactly what `renault.py`'s own trim-heading parsing produces for
`ExtractedVariant.trim` - so a lookup by trim name matches directly.

Unlike Dacia's own trim lineups (always a strict linear chain - Essential ->
Expression -> Journey -> Extreme), Renault's "navíc oproti <trim>" deltas
are NOT always chained to the immediately preceding section: Espace's own
page 3 has "ESPRIT ALPINE" and "ICONIC" BOTH declared "navíc oproti Techno"
(not "navíc oproti Esprit Alpine" for Iconic) - two sibling trims each
built on top of the same base, not a chain of three. A single running
"carry forward" accumulator (Dacia's own approach) would silently fold
Esprit Alpine's own extra items into Iconic's list too, which the source
text itself doesn't claim. `_parse_equipment_lines` instead parses which
trim name each "navíc oproti <X>" delta actually names (`_DELTA_RE`) and
looks up that trim's own already-finalized item dict from what's already
been parsed - correct for both a true chain (Dacia's shape, still handled
the same way since the referenced trim there is always the true
predecessor) and Espace's branching shape alike.

The other five documents - Austral, Symbioz, Megane, and the two e-tech
Renault 4/Renault 5 fixtures - print this same section as TWO SIDE-BY-SIDE
COLUMNS instead (verified via `page.extract_words()`'s own x0 coordinates:
Renault 4's page 3 has a left column of bullets/items starting at x0≈31-39
and a right column at x0≈305-313, with category sub-headings, e.g. "Aktivní
a pasivní bezpečnost" / "Nabíjení", interleaved on the same physical row),
which `extract_text()` linearizes into single lines carrying TWO "•"-led
items each (e.g. "• ABS s rozdělovačem brzdného účinku • vyhřívání
baterie") - naively feeding such a line through the single-column algorithm
above would glue two unrelated item names into one fabricated string. Since
Renault 4/5's own two-trim continuation (page 4, "iConiC"/"iConiC Plein
SuD", both "navíc oproti techno") depends on a base ("techno") that only
ever appears on the two-column page 3, `parse_standard_equipment` bails out
of the WHOLE document (not just the offending page) the moment any one of
its own equipment pages shows this shape (`_has_two_column_layout`) -
otherwise the two-trim page would silently produce an INCOMPLETE-looking
but not obviously wrong "iConiC has only its own 4 items" result, which is
worse than skipping outright. A known, accepted gap for these five models
(same "vertical slice, then generalize" precedent as `skoda_equipment.py`'s
own package-matrix gap), not attempted here - reconstructing the real
column layout would need `page.extract_words()`'s own x0 coordinates
instead of `extract_text()`, a materially different approach from the one
this module takes.
"""
from __future__ import annotations

import re

import pdfplumber

_SECTION_MARKER = "hlavní prvky sériové výbavy"
_BULLET = "•"
_DELTA_RE = re.compile(r"navíc oproti\s+(.+?):?\s*\Z", re.IGNORECASE)


def _has_two_column_layout(text: str) -> bool:
    """Args:
        text: One page's `extract_text()` output.

    Returns:
        `True` if any line on the page carries 2+ "•" bullets - the
        telltale sign of the two-side-by-side-columns layout this module
        doesn't attempt to parse (see module docstring).
    """
    return any(line.count(_BULLET) >= 2 for line in text.splitlines())


def _parse_equipment_lines(lines: list[str]) -> dict[str, dict[str, str]]:
    """Args:
        lines: Every non-empty, stripped line from one or more consecutive
            single-column "hlavní prvky sériové výbavy" pages, in reading
            order (callers must already have ruled out the two-column
            layout via `_has_two_column_layout` - see module docstring).

    Returns:
        `{trim: {item_name: "STANDARD"}}` for every trim section found,
        each trim's dict already resolved to its full standard equipment -
        its own section's items plus, for a "navíc oproti <trim>" delta
        section, that referenced trim's own already-finalized items (see
        module docstring for why this is looked up by name rather than
        carried forward as one running accumulator).
    """
    heading_indices = {
        i - 1 for i, line in enumerate(lines) if i > 0 and line.lower().startswith(_SECTION_MARKER)
    }

    trim_items: dict[str, dict[str, str]] = {}
    current_trim: str | None = None
    current_items: dict[str, str] = {}
    buffer: list[str] = []

    def flush_item() -> None:
        name = " ".join(buffer).strip()
        if name and current_trim is not None:
            current_items[name] = "STANDARD"
        buffer.clear()

    for i, line in enumerate(lines):
        if i in heading_indices:
            continue

        if i > 0 and line.lower().startswith(_SECTION_MARKER):
            flush_item()
            if current_trim is not None:
                trim_items[current_trim] = dict(current_items)

            current_trim = lines[i - 1].title().strip()
            delta = _DELTA_RE.search(line)
            current_items = dict(trim_items.get(delta.group(1).title().strip(), {})) if delta else {}
            continue

        if line.startswith(_BULLET):
            flush_item()
            rest = line[1:].strip()
            if rest:
                buffer.append(rest)
            continue

        if current_trim is not None:
            buffer.append(line)  # wrapped continuation of the current bullet item

    flush_item()
    if current_trim is not None:
        trim_items[current_trim] = dict(current_items)
    return trim_items


def parse_standard_equipment(pdf: pdfplumber.PDF) -> dict[str, dict[str, str]]:
    """Args:
        pdf: The opened Renault price-list PDF.

    Returns:
        `{trim: {item_name: "STANDARD"}}`, merged across every page that
        carries a "hlavní prvky sériové výbavy" section - `{}` if no such
        page was found, or if any one of them uses the two-side-by-side-
        columns layout this module doesn't parse (see module docstring for
        why a partial result would be worse than none here).
    """
    marker_pages: list[str] = []
    for page in pdf.pages:
        text = page.extract_text() or ""
        if _SECTION_MARKER in text.lower():
            marker_pages.append(text)

    if not marker_pages or any(_has_two_column_layout(text) for text in marker_pages):
        return {}

    lines: list[str] = []
    for text in marker_pages:
        lines.extend(line.strip() for line in text.splitlines() if line.strip())

    return _parse_equipment_lines(lines)

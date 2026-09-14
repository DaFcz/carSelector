"""Extracts standard equipment from Dacia price lists' own "SÉRIOVÁ VÝBAVA"
overview page (page 4 or 5, right after the price table — one section per
trim, e.g. "ESSENTIAL" / "Hlavní prvky sériové výbavy:" followed by a bullet
list). Unlike Škoda's "Samostatné prvky výbavy" page (`skoda_equipment.py`),
there's no availability matrix or price here — every listed item is simply
`STANDARD` for that trim (Dacia's price lists don't expose a-la-carte paid
options anywhere), so `ExtractedVariant.equipment_surcharge` is never
populated by this module.

Two distinct section-header phrasings appear across the six models'
fixtures, both starting "Hlavní prvky sériové výbavy":
- Plain ("...výbavy:") — this trim's own COMPLETE list (Duster, Bigster: all
  four trims use this form; every other model's first trim always does too,
  naturally, since there's no lower trim to reference).
- Delta ("...výbavy navíc oproti <trim>:") — this trim gets everything the
  referenced trim has PLUS this section's own items (Sandero, Sandero
  Stepway, Spring, Jogger use this for every trim after their first).

Which form is used is read per-section (the "navíc" substring), not assumed
per model — carrying forward an accumulated running set only when a section
says so, and resetting to a fresh set otherwise, reproduces both without
hardcoding which models use which style.

Trim names are matched case-insensitively against `_KNOWN_TRIMS` rather than
parsed as free text, since the same smallcaps-style font issue documented in
`dacia.py` (mixed-case glyphs, e.g. "ExpREssION") shows up on this page too.
"""
from __future__ import annotations

import pdfplumber

_SECTION_MARKER = "hlavní prvky sériové výbavy"
_KNOWN_TRIMS = {
    "ESSENTIAL": "Essential",
    "EXPRESSION": "Expression",
    "JOURNEY": "Journey",
    "EXTREME": "Extreme",
}


def _parse_equipment_text(text: str) -> dict[str, dict[str, str]]:
    """Args:
        text: `extract_text()` output of one page containing at least one
            "Hlavní prvky sériové výbavy..." section (see module docstring).

    Returns:
        `{trim: {item_name: "STANDARD"}}` for every trim section found on
        this page, each trim's dict already resolved to its full standard
        equipment (deltas folded in, see module docstring).
    """
    trim_items: dict[str, dict[str, str]] = {}
    accumulated: dict[str, str] = {}
    current_trim: str | None = None
    buffer: list[str] = []

    def flush_item() -> None:
        name = " ".join(buffer).strip()
        if name and current_trim is not None:
            accumulated[name] = "STANDARD"
        buffer.clear()

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("str. "):
            continue

        canonical_trim = _KNOWN_TRIMS.get(line.upper())
        if canonical_trim is not None:
            flush_item()
            if current_trim is not None:
                trim_items[current_trim] = dict(accumulated)
            current_trim = canonical_trim
            continue

        if line.lower().startswith(_SECTION_MARKER):
            flush_item()
            if "navíc" not in line.lower():
                accumulated = {}
            continue

        if line.startswith("•"):
            flush_item()
            rest = line[1:].strip()
            if rest:
                buffer.append(rest)
            continue

        if current_trim is not None:
            buffer.append(line)  # wrapped continuation of the current bullet item

    flush_item()
    if current_trim is not None:
        trim_items[current_trim] = dict(accumulated)
    return trim_items


def parse_standard_equipment(pdf: pdfplumber.PDF) -> dict[str, dict[str, str]]:
    """Args:
        pdf: The opened Dacia price-list PDF.

    Returns:
        `{trim: {item_name: "STANDARD"}}`, merged across every page that
        carries a "Hlavní prvky sériové výbavy" section (in practice
        exactly one page per fixture, but nothing here assumes that) — `{}`
        if the page isn't found (e.g. a future document layout change).
    """
    result: dict[str, dict[str, str]] = {}
    for page in pdf.pages:
        text = page.extract_text() or ""
        if _SECTION_MARKER not in text.lower():
            continue
        for trim, items in _parse_equipment_text(text).items():
            result.setdefault(trim, {}).update(items)
    return result

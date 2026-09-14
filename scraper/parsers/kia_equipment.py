"""Extracts standard equipment from Kia price lists' own "Hlavní prvky
standardní výbavy" bullet page (page 3, right after the price table —
verified against all four fixtures: kia_ceed_sw_cenik.pdf,
kia_niro_cenik.pdf, kia_sportage_hev_phev_cenik.pdf,
kia_sportage_ice_cenik.pdf). Same convention as Dacia's "Hlavní prvky
sériové výbavy" page (`dacia_equipment.py`): one bullet list per trim, no
price anywhere on it, so `ExtractedVariant.equipment_surcharge` is never
populated here either. Kia's own "STANDARDNÍ VÝBAVA A VÝBAVA NA PŘÁNÍ"
availability-matrix page (right after this one) is NOT parsed by this
module — unlike Škoda's/Mazda's own matrices, its cells mix plain "●"
marks, per-trim descriptive text (e.g. a mirror housing's paint finish),
bare "Paket <name>" references (the item isn't itself standard/optional,
only bundled in a named package), and — on the "Výbava na přání" section
specifically — prices that can differ by trim for the same item, with
many of its own item names wrapping across several lines. Reliably
telling those cases apart needs more x-position engineering than this
pass covers; treated as a known, documented gap rather than guessed at,
same "skip rather than guess" precedent as this page's own wrapped-name
handling below.

Unlike Dacia, where a delta section ("...výbavy navíc oproti <trim>:")
always references the trim immediately before it in the model's trim
list, Kia names the referenced trim EXPLICITLY in its own heading text
("Hlavní prvky standardní výbavy oproti <trim>:"), and that reference is
not always the immediately preceding section: on both Sportage fixtures,
TOP is offered "oproti Exclusive", skipping over BLACK EDITION even
though BLACK EDITION's own section comes between them in reading order.
Resolving each trim's full equipment by NAME (`_resolve`, memoized)
rather than carrying forward one running accumulator (Dacia's approach)
reproduces this correctly.

Ceed SW's own bullet page references a base trim, "Comfort", that never
appears as its own section there (only SPIN and TOP do — matching Ceed
SW's own price table, which likewise only prices SPIN/TOP rows, see
`kia.py`) or anywhere else in that fixture. For that model, `_resolve`
treats the unresolvable "Comfort" reference as an empty base rather than
an error, so SPIN/TOP still come back with their own confirmed delta
items — a known, accepted undercount (never a fabricated item) rather
than guessing what Comfort might contain.

Trim headings are matched by exact text against `trims` — the same trim
strings `KiaParser.parse` already extracted from the price table's own
heading lines directly above each row (same "look up the already-known
trim list instead of re-parsing this page's own formatting" principle as
`mazda_equipment.py`) — rather than treating any non-bullet line here as
a heading, since a bare line can just as easily be the model title
("NOVÉ NIRO MY27") or the "Ilustrační fotografie." caption both Sportage
fixtures repeat after every section (both are simply skipped: matched
against neither a trim name nor the marker/bullet formats).

One heading line, on the Niro fixture only (the "Style" section's own
marker line), has every character doubled up ("HHllaavvnníí
pprrvvkkyy..." for "Hlavní prvky...") — the same glyph-duplication
artifact bold text runs occasionally produce elsewhere in these
documents (e.g. the "VÁŠ DEALER" footer on both Sportage fixtures, verified
via `page.extract_text()`). `_collapse_repeated_chars` is tried as a
fallback only when the marker regex doesn't match a line outright, so it
can never alter an already-well-formed line.

Items whose name wraps across multiple physical lines are still captured
here (unlike `skoda_equipment.py`'s standalone-item page) — a wrapped
bullet's continuation lines carry no "•" of their own and simply keep
appending to the item currently being built, same convention as
`dacia_equipment.py`."""
from __future__ import annotations

import re
from itertools import groupby

import pdfplumber

_MARKER_RE = re.compile(
    r"^hlavní prvky standardní výbavy(?:\s+oproti\s+(?P<ref>.+))?:\s*$",
    re.IGNORECASE,
)
_SKIP_LINES = {"ilustrační fotografie."}


def _collapse_repeated_chars(line: str) -> str:
    """Args:
        line: One raw text line.

    Returns:
        `line` with every run of consecutive identical characters
        collapsed to one — undoes the doubled-glyph artifact described in
        the module docstring. Safe to use only as a fallback match (see
        `_match_marker`): a well-formed line with a genuine double letter
        would be corrupted by this.
    """
    return "".join(ch for ch, _ in groupby(line))


def _match_marker(line: str) -> re.Match[str] | None:
    """Args:
        line: One stripped text line.

    Returns:
        The `_MARKER_RE` match against `line`, or — only if that fails —
        against its `_collapse_repeated_chars` form (see module
        docstring's doubled-glyph note). `None` if neither matches.
    """
    match = _MARKER_RE.match(line)
    if match is not None:
        return match
    collapsed = _collapse_repeated_chars(line)
    return _MARKER_RE.match(collapsed) if collapsed != line else None


def _parse_page_sections(text: str, trims: set[str]) -> dict[str, tuple[str | None, dict[str, str]]]:
    """Args:
        text: `extract_text()` output of one page that may carry one or
            more trim sections (heading line from `trims`, marker line,
            then bullet items — see module docstring).
        trims: This document's own trim names (exact text, from
            `KiaParser.parse`'s already-extracted variants).

    Returns:
        `{trim: (referenced_trim_or_None, {item_name: "STANDARD"})}` for
        every section on this page whose heading exactly matches a name
        in `trims` — `referenced_trim_or_None` is the "oproti <trim>"
        target read off that section's own marker line, `None` for a
        plain (non-delta) marker.
    """
    sections: dict[str, tuple[str | None, dict[str, str]]] = {}
    current_trim: str | None = None
    current_ref: str | None = None
    items: dict[str, str] = {}
    buffer: list[str] = []

    def flush_item() -> None:
        name = " ".join(buffer).strip()
        if name and current_trim is not None:
            items[name] = "STANDARD"
        buffer.clear()

    def flush_section() -> None:
        flush_item()
        if current_trim is not None:
            sections[current_trim] = (current_ref, dict(items))

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.lower() in _SKIP_LINES:
            continue

        if line in trims:
            flush_section()
            current_trim = line
            current_ref = None
            items = {}
            continue

        marker = _match_marker(line)
        if marker is not None:
            flush_item()
            ref = marker.group("ref")
            current_ref = ref.strip() if ref is not None else None
            continue

        if line.startswith("•"):
            flush_item()
            rest = line[1:].strip()
            if rest:
                buffer.append(rest)
            continue

        if current_trim is not None:
            buffer.append(line)  # wrapped continuation of the current bullet item

    flush_section()
    return sections


def parse_standard_equipment(pdf: pdfplumber.PDF, trims: list[str]) -> dict[str, dict[str, str]]:
    """Args:
        pdf: The opened Kia price-list PDF.
        trims: This document's own trim names in the exact casing/text
            `KiaParser.parse` already produces for `ExtractedVariant.trim`
            (see module docstring for why headings are matched against
            these instead of parsed freely).

    Returns:
        `{trim: {item_name: "STANDARD"}}` for every trim in `trims` whose
        own section was found (deltas resolved by name — see module
        docstring's `_resolve`/TOP-oproti-Exclusive note) — a trim with no
        matching section on any page (or whose only reference is
        unresolvable, see the Ceed SW/Comfort note) simply gets whatever
        was confidently read, which may be `{}`.
    """
    known = set(trims)
    own: dict[str, tuple[str | None, dict[str, str]]] = {}
    for page in pdf.pages:
        text = page.extract_text() or ""
        if "hlavní prvky standardní výbavy" not in text.lower():
            continue
        own.update(_parse_page_sections(text, known))

    resolved: dict[str, dict[str, str]] = {}

    def resolve(trim: str, seen: frozenset[str]) -> dict[str, str]:
        if trim in resolved:
            return resolved[trim]
        ref, items = own[trim]
        base = resolve(ref, seen | {trim}) if ref is not None and ref in own and ref not in seen else {}
        result = {**base, **items}
        resolved[trim] = result
        return result

    return {trim: resolve(trim, frozenset()) for trim in trims if trim in own}

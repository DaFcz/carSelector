"""Parser for Ford's per-model "Ceník" price lists (verified against real
PDFs downloaded 2026-09-07 from ford.cz's asset CDN, effective 30 June/
1 July/1 September 2026 depending on model — see scraper/tests/fixtures/
ford_*.pdf). Covers Puma, Kuga, Mustang and Bronco - see module docstring's
"Scope" section below for why the rest of the current CZ lineup isn't
included yet.

Every model's price table is a genuine two-axis matrix - trim (column) by
engine/transmission (row) - unlike every other brand parsed here, which is
effectively a one-column list (a trim heading, then its engine rows). One
cell reads, e.g. (Kuga, page 2):

    Titanium  Top Edition  ST-Line  ST-Line X  Active X  BlueCruise Edition
    649 900   -            699 900  752 900    752 900   -
    725 000   -            775 000  858 000    858 000   -

Each engine row is THREE things stacked vertically in the source (verified
against a rendered page image, not just extracted text - naive text
extraction interleaves them in a confusing order): a "Zvýhodněná cena"
(discounted-with-financing price) row, the engine/transmission description
(Motor/Palivo/Výkon/Převodovka/Pohon - whichever of these columns this
model's header has - wrapping onto 1-2 lines of its own), then a "Základní
cena" (base list price) row - `price` is read from the base row, matching
every other brand's "list price, not a promotional one" convention (Kia's
CENÍKOVÁ CENA, Mazda's CENA, ...). A column with no offering for that row
reads "-" instead of a price; that dash can land on any of the three
lines depending on how many lines the description itself wraps to, so
`parse` doesn't assume a fixed 3-line shape - it tracks "the last two
lines that carried trim-column content (digits or a dash)" as the
discount/base pair for whatever description text accumulated between them
(see `_classify_row_words`/`parse`'s own comments).

Trim columns are read off the header dynamically, not hardcoded - the
header itself needs the same word-clustering technique as Dacia's engine
column (`_HEADER_GAP_THRESHOLD`, ~1.6-1.7pt within one trim's own name,
21.8pt+ between trims, verified against real coordinates) because a
multi-word trim name ("ST-Line X", "BlueCruise Edition") can wrap onto a
line of its own above or below the header's main line. Once a trim's own
left edge is known, `_pdf_layout.column_for_x` (the same helper Škoda's
parser uses) assigns each data word to a column and - critically - keeps a
price split across multiple words by the thousands separator (e.g. "1"
"017" "000") in that SAME column rather than bleeding into the next one.

Everything left of the first trim column (Motor/Palivo/Výkon/Převodovka/
Pohon - which of these a given model's header has varies, see
`_LEFT_LABELS`) is concatenated in reading order into one engine
descriptor string, used both for `variant_name` and for classifying
powertrain via Ford's own "(mHEV)"/"(HEV)"/"(PHEV)" markers on the engine
name (`_classify_powertrain`, same precedence order as Kia's PHEV/MHEV/HEV/
ICE check).

Scope: Ford's CZ lineup has ~10 current models, but only Puma/Kuga/Mustang/
Bronco are covered here - the rest don't fit this parser's column model
and are a known gap for a follow-up, not silently mis-parsed:
- Explorer, Puma Gen-E and Mustang Mach-E (all-electric) add a "Dojezd"
  (range) figure that's either its own per-trim, "/"-separated multi-value
  column (Explorer) sitting BETWEEN the description and the price columns,
  or a single value folded into the description (Mustang Mach-E) - the
  former breaks the "everything left of the first trim column is just
  description text" assumption this parser relies on, and neither
  document's own true trim/price structure has been hand-verified yet the
  way Puma/Kuga/Mustang/Bronco have.
- Tourneo Courier/Connect/Custom use a completely different "AKČNÍ CENÍK"
  layout (a single "bez DPH (s DPH)" price per cell, not a discount/base
  pair) - a different parser's worth of work, not a variant of this one.
- Puma ST and Tourneo Custom MS-RT are single-trim special-edition
  documents whose header replaces "Motor" with "Benzín", which
  `_is_header_line` doesn't recognize (so they're simply skipped, not
  mis-parsed) - low value for the extra special-casing given they're a
  single row each.
- Capri (electric-only) wasn't reachable from this environment to verify
  at all (see `discovery/ford.py`'s module docstring).
`DaciaDiscoverer`-style "only 4 of X models" precedent: matches Kia/Toyota/
Hyundai's "one document format per iteration" rollout, not a permanent
scope decision - see doc/arch/webScraping/IMPLEMENTATION_PLAN.md.

Like every other brand here, the cover/disclaimer text reads "Všechny ceny
jsou platné od D. M. RRRR" (not "Platnost od ...", `_pdf_layout.
extract_release_date`'s pattern), so `release_date` stays None;
VariantRepository falls back to the download date. The same marker text
(`_END_OF_TABLE_MARKER`) doubles as the "stop reading data rows" signal for
`parse`, since the legal/financing disclaimer paragraph directly below
every price table always opens with it."""

from __future__ import annotations

from pathlib import Path

import pdfplumber

from ._pdf_layout import column_for_x, group_into_lines, line_text
from .base import BaseParser, ExtractedVariant

_MARKETING_PREFIXES = ("NOVÁ ", "NOVÝ ", "NOVÉ ")
_LEFT_LABELS = {"Motor", "Palivo", "Výkon", "Převodovka", "Pohon"}
_END_OF_TABLE_MARKER = "Všechny ceny jsou platné"
_HEADER_GAP_THRESHOLD = 15.0  # pt; intra-trim-name gaps are ~1.6-1.7pt, the smallest real column gap is 21.8pt+
_HEADER_TOP_WINDOW = (
    8.0  # pt; captures a trim header word wrapped onto its own line just above/below the main header line
)


def _extract_model_name(pdf: pdfplumber.PDF) -> str:
    """Args:
        pdf: The opened price-list PDF.

    Returns:
        The cover page's own model name (its first line, marketing
        prefix stripped, title-cased - the cover is printed in all
        caps, e.g. "NOVÁ PUMA" -> "Puma", "KUGA" -> "Kuga").
    """
    cover_text = pdf.pages[0].extract_text() or ""
    lines = cover_text.strip().splitlines()
    if not lines:
        return "unknown"
    first_line = lines[0].strip()
    for prefix in _MARKETING_PREFIXES:
        if first_line.startswith(prefix):
            first_line = first_line[len(prefix) :].strip()
            break
    return first_line.title()


def _is_header_line(line: list[dict]) -> bool:
    texts = {w["text"] for w in line}
    return "Motor" in texts and "Převodovka" in texts


def _cluster_by_gap(words: list[dict], threshold: float) -> list[list[dict]]:
    """Args:
        words: Words already sorted left to right.
        threshold: Minimum x-gap (pt) that starts a new cluster.

    Returns:
        `words` split into clusters wherever the gap to the previous
        word's `x1` exceeds `threshold`.
    """
    if not words:
        return []
    clusters: list[list[dict]] = [[words[0]]]
    for word in words[1:]:
        if word["x0"] - clusters[-1][-1]["x1"] > threshold:
            clusters.append([word])
        else:
            clusters[-1].append(word)
    return clusters


def _trim_columns(lines: list[list[dict]], header_index: int) -> list[tuple[str, float]]:
    """Args:
        lines: The whole page's lines (see `_pdf_layout.group_into_lines`).
        header_index: Index into `lines` of the line `_is_header_line` matched.

    Returns:
        `(trim_name, left_x)` pairs, left to right - `left_x` is the
        trim's own left edge, for `_pdf_layout.column_for_x`. Gathers
        every word within `_HEADER_TOP_WINDOW` of the header line's own
        `top` (not just the header line itself) so a trim name wrapped
        onto its own line just above/below it (e.g. "BlueCruise" above,
        "Edition" below the main header line) is still included, then
        clusters everything but the known left-side column labels by
        x-gap - see module docstring for the gap sizes this relies on.
    """
    header_top = lines[header_index][0]["top"]
    header_words = [word for line in lines if abs(line[0]["top"] - header_top) <= _HEADER_TOP_WINDOW for word in line]
    trim_words = sorted((w for w in header_words if w["text"] not in _LEFT_LABELS), key=lambda w: w["x0"])
    return [
        (" ".join(w["text"] for w in cluster), cluster[0]["x0"])
        for cluster in _cluster_by_gap(trim_words, _HEADER_GAP_THRESHOLD)
    ]


def _classify_row_words(words: list[dict], trim_columns: list[tuple[str, float]]) -> tuple[list[dict], dict[str, str]]:
    """Splits one line's words into the free-text part (left of the first
    trim column) and this line's per-trim cell content.

    Args:
        words: One line's words (a data row - may carry description text,
            trim-column content, or both, see module docstring).
        trim_columns: This page's `(name, left_x)` pairs from `_trim_columns`.

    Returns:
        `(left_words, cells)` - `left_words` in original order (for the
        engine descriptor); `cells` maps trim name -> `"-"` or a
        concatenated digit string (multi-word prices, e.g. "1" "017"
        "000", are joined via `column_for_x` keeping same-column
        continuations together - see module docstring). A trim column
        whose content on this line is neither all-digit nor a lone "-"
        (shouldn't happen, but see e.g. a stray header continuation word)
        is simply omitted, not guessed at.
    """
    anchors = [x0 for _, x0 in trim_columns]
    names = [name for name, _ in trim_columns]
    boundary = anchors[0] - 5

    left = [w for w in words if w["x0"] < boundary]
    right = [w for w in words if w["x0"] >= boundary]

    by_column: dict[str, list[dict]] = {}
    for word in right:
        name = names[column_for_x(word["x0"], anchors)]
        by_column.setdefault(name, []).append(word)

    cells: dict[str, str] = {}
    for name, column_words in by_column.items():
        column_words.sort(key=lambda w: w["x0"])
        texts = [w["text"] for w in column_words]
        if texts == ["-"]:
            cells[name] = "-"
        elif all(t.isdigit() for t in texts):
            cells[name] = "".join(texts)
    return left, cells


def _classify_powertrain(descriptor: str) -> str:
    lowered = descriptor.lower()
    if "phev" in lowered:
        return "PHEV"
    if "mhev" in lowered:
        return "MHEV"
    if "hev" in lowered:
        return "HEV"
    return "ICE"


class _EngineGroup:
    """Accumulates one engine/transmission row's description text and its
    (discount, base) price-cell pairs across however many physical lines
    it spans - see module docstring for why that count varies."""

    def __init__(self) -> None:
        self.desc_words: list[str] = []
        self.price_rows: list[dict[str, str]] = []
        self.unavailable: set[str] = set()
        self.raw_lines: list[str] = []

    def add_line(self, left: list[dict], cells: dict[str, str], text: str) -> None:
        """Ignores everything on a line once the group already has its
        full (discount, base) pair - a real engine's own description is
        always fully assembled by then (it sits BETWEEN the two price
        rows, see module docstring), so anything still arriving after
        that point is trailing non-table content (e.g. Mustang's own
        "Dodatečné zvýhodnění ... skladové vozy ..." bonus note, printed
        directly below the last price row, before the legal disclaimer
        `_END_OF_TABLE_MARKER` catches) - not part of THIS row, and not
        yet the next one either (`is_ready_for` is what starts a new
        group, from its own first real price line)."""
        if len(self.price_rows) >= 2:
            return
        prices = {name: value for name, value in cells.items() if value != "-"}
        if prices:
            self.price_rows.append(prices)
        self.unavailable |= {name for name, value in cells.items() if value == "-"}
        if left:
            self.desc_words.extend(w["text"] for w in left)
        if text:
            self.raw_lines.append(text)

    def is_ready_for(self, cells: dict[str, str]) -> bool:
        """True if this line's `cells` would be a THIRD price row - i.e.
        this group already has its full discount+base pair and a new
        engine row is starting."""
        has_price = any(value != "-" for value in cells.values())
        return has_price and len(self.price_rows) >= 2

    def variants(self, model: str, source_page: int) -> list[ExtractedVariant]:
        """Returns:
        One `ExtractedVariant` per available trim, or `[]` if this
        group never completed a (discount, base) pair - an
        incomplete/malformed group is dropped, not guessed at.
        """
        if len(self.price_rows) != 2:
            return []
        _discount, base = self.price_rows
        descriptor = " ".join(self.desc_words).strip()
        if not descriptor:
            return []
        raw_text = " | ".join(self.raw_lines)
        powertrain = _classify_powertrain(descriptor)
        return [
            ExtractedVariant(
                model=model,
                trim=trim,
                variant_name=f"{model} {trim} {descriptor}",
                price=float(price_text),
                currency="CZK",
                source_page=source_page,
                raw_text=raw_text,
                powertrain=powertrain,
            )
            for trim, price_text in base.items()
            if trim not in self.unavailable
        ]


class FordParser(BaseParser):
    brand = "ford"
    powertrain = "ICE"  # nominal default; the actual powertrain is per-row, see _classify_powertrain

    def parse(self, pdf_path: Path) -> list[ExtractedVariant]:
        """See module docstring for the trim/engine matrix shape and the
        current model scope.

        Args:
            pdf_path: Local path to a downloaded Ford price-list PDF.

        Returns:
            One `ExtractedVariant` per (trim, engine) cell that has a
            price, across every page with a "Motor ... Převodovka ..."
            header.
        """
        variants: list[ExtractedVariant] = []

        with pdfplumber.open(pdf_path) as pdf:
            model = _extract_model_name(pdf)

            for page in pdf.pages:
                lines = group_into_lines(page.extract_words())
                header_index = next((i for i, line in enumerate(lines) if _is_header_line(line)), None)
                if header_index is None:
                    continue  # page without a price table (specs, equipment, accessories, ...)

                trim_columns = _trim_columns(lines, header_index)
                if not trim_columns:
                    continue

                group = _EngineGroup()
                for line in lines[header_index + 1 :]:
                    text = line_text(line)
                    if text.startswith(_END_OF_TABLE_MARKER):
                        break
                    if _is_header_line(line):
                        continue  # a wrapped header continuation line (e.g. "Edition"), not a data row

                    left, cells = _classify_row_words(line, trim_columns)
                    if group.is_ready_for(cells):
                        variants.extend(group.variants(model, page.page_number))
                        group = _EngineGroup()
                    group.add_line(left, cells, text)

                variants.extend(group.variants(model, page.page_number))

        return variants

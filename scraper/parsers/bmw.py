"""Parser for BMW's combined "Ceník základních modelů" price list (verified
against the real PDF downloaded 2026-08-29 from bmw.cz, effective from
1 July 2026).

Like Mercedes-Benz, one BMW document covers the entire current lineup - but
unlike Mercedes-Benz's 74-page interactive-brochure export (see
mercedes_benz.py's module docstring) or Mazda's overlapping-text-layer one
(see mazda.py's module docstring), this is a genuinely plain 6-page price
table, closer in spirit to Škoda's single-listing-page simplicity:
`page.extract_words()` needs no de-duplication or font-size filtering here,
just the usual `_pdf_layout.group_into_lines`.

Each model is its own section, headed by a line like "BMW řady 3 Sedan
(G20) / M3 Sedan (G80)" or "BMW X1 (U11)" — `_extract_model` turns that
into a plain name ("3 Series Sedan", "X1") by dropping the "BMW "/"Nový "
marketing prefix, the trailing "(chassis code)", and anything from a "/"
onward (the M-performance chassis annotation - its rows are already part
of the same section, e.g. "M3 Competition M xDrive" is just another row
under "BMW řady 3 Sedan"). "řady N" becomes "N Series". A section that
continues onto a second page repeats its own heading suffixed "-
pokračování" ("continued") - stripped before the same transform, so it
maps back to the same model name rather than starting a new one.

A data row reads e.g.:

    123 xDrive 4 1 998 160/218 134 5,9 890 661 1 077 700

trim designation, cylinder count ("-" for EVs), displacement in cm³ ("-"
for EVs, always a 4-digit number split "N NNN" by the thousands separator
otherwise), power "kW/hp", CO2 g/km, combined consumption (contains a
comma, e.g. "5,9" - never a bare digit token, which is what lets it mark
the boundary between CO2 and the price columns), then TWO prices (ex-VAT,
incl-VAT). `trim` is just the row's own designation and `price` the final
(incl-VAT) column; cylinder count/CO2/consumption aren't part of
`ExtractedVariant`'s schema and are read then discarded, same "the columns
that don't map to a schema field are read then skipped, not stored"
approach as every other parser here - displacement and power ARE kept,
folded into `variant_name` rather than dropped, for a reason that has
nothing to do with display: see `_parse_row`'s comment on
`powertrain_signature`.

The row is anchored on its power column (`\\d+/\\d+`, a shape nothing else
on the line matches) rather than parsed left-to-right, since the trim
designation's own length varies (one word - "M5" - up to four - "M3
Competition M xDrive"): cylinder count and displacement are read backward
from the power column (displacement is always exactly one word if "-",
otherwise exactly two - every real engine here is a 4-digit cm³ figure,
verified across all ~180 rows in the fixture), and the price columns are
read forward. The two prices can't be told apart by counting digit-tokens
alone (a 7-digit price and the 6-digit price before it are BOTH split into
3-digit continuation words with no reliable break, e.g. "656 446 794 300"
for a row where ex-VAT is 656 446 and incl-VAT is 794 300 - every token
after the first is exactly 3 digits) - resolved the same way as Mercedes-
Benz's row-2 price (see that parser's module docstring): consecutive words
belonging to the SAME price sit only ~2-3pt apart, while the real gap
between the ex-VAT and incl-VAT columns is 26pt+ (verified against real
word x0/x1 coordinates) - `_last_price` walks the trailing digit run from
the right and stops at the first gap past `_COLUMN_GAP_THRESHOLD`, keeping
only the rightmost (incl-VAT) group, matching the "price = the VAT-
inclusive consumer list price" convention used for every other brand here.

Powertrain is classified from the MODEL name for electric variants (a
lowercase "i" immediately followed by a digit or "X" - "i3"/"i4"/"i5"/
"i7"/"iX"/"iX1"/"iX2"/"iX3" - each is its own section, entirely separate
from the combustion one it's named after) and per-ROW for plug-in hybrids,
which are mixed into their combustion model's own section rather than
getting one of their own (e.g. "330e" is a row under "BMW řady 3 Sedan",
alongside plain "320i" rows) - BMW's plug-in hybrid trims always end in a
2-3 digit number immediately followed by a lowercase "e" (`_PHEV_RE`),
distinct from the petrol "...i" suffix (e.g. "230i") or the diesel "...d"
suffix (e.g. "320d").

Like Kia/Toyota/Hyundai/Mercedes-Benz/Mazda (and unlike Škoda/VW), the
cover/disclaimer text states a production-month WINDOW ("Od 1. července
2026 pro produkční měsíce červenec 2026 až říjen 2026"), not a single
"Platnost od D. M. RRRR" date - `_pdf_layout.extract_release_date` doesn't
match this format, so `release_date` stays None here too, and
VariantRepository falls back to the download date."""

from __future__ import annotations

import re
from pathlib import Path

import pdfplumber

from ._pdf_layout import group_into_lines, line_text
from .base import BaseParser, ExtractedVariant

_MARKETING_PREFIXES = ("Nový ", "Nová ", "Nové ")
_SERIES_RE = re.compile(r"^řady (\d)\s*(.*)$")
_POWER_RE = re.compile(r"^\d+/\d+$")
_PHEV_RE = re.compile(r"\b\d{2,3}e\b")
_COLUMN_GAP_THRESHOLD = 15.0  # pt; continuation gaps are ~2-3pt, the real column gap is 26pt+


def _extract_model(text: str) -> str | None:
    """Args:
        text: A candidate section-heading line's full text.

    Returns:
        The canonical model name (see module docstring for the
        transform), or `None` if `text` isn't a section heading at all
        (doesn't start with "BMW", ignoring a marketing prefix).
    """
    text = re.sub(r"\s*-\s*pokračování\s*$", "", text.strip())
    text = text.split(" / ")[0].strip()
    for prefix in _MARKETING_PREFIXES:
        if text.startswith(prefix):
            text = text[len(prefix) :]
            break
    if not text.startswith("BMW "):
        return None
    text = text[len("BMW ") :]
    text = re.sub(r"\s*\([A-Z][A-Z0-9]{1,3}\)\s*$", "", text).strip()
    match = _SERIES_RE.match(text)
    if match:
        number, rest = match.groups()
        text = f"{number} Series" + (f" {rest}" if rest else "")
    return text


def _is_electric(model: str) -> bool:
    return model.startswith("i") and len(model) > 1 and (model[1].isdigit() or model[1] == "X")


def _last_price(tail_words: list[dict]) -> float | None:
    """Args:
        tail_words: The trailing run of pure-digit words at the end of a
            row - contains both price columns with no reliable break
            between them (see module docstring).

    Returns:
        The RIGHTMOST digit group's value (the incl-VAT price), or `None`
        if `tail_words` is empty.
    """
    if not tail_words:
        return None
    digits = tail_words[-1]["text"]
    next_x0 = tail_words[-1]["x0"]
    for word in reversed(tail_words[:-1]):
        if next_x0 - word["x1"] > _COLUMN_GAP_THRESHOLD:
            break
        digits = word["text"] + digits
        next_x0 = word["x0"]
    return float(digits) if digits.isdigit() else None


def _parse_row(line: list[dict], model: str, source_page: int) -> ExtractedVariant | None:
    """Args:
        line: One line's words (see module docstring for the row shape).
        model: The section this row belongs to (from `_extract_model`).
        source_page: 1-based page number `line` was read from.

    Returns:
        The row's `ExtractedVariant`, or `None` if `line` isn't a data
        row (no power-column word) or its trailing price can't be read.
    """
    power_idx = next((i for i, w in enumerate(line) if _POWER_RE.match(w["text"])), None)
    if power_idx is None:
        return None
    power = line[power_idx]["text"]

    if line[power_idx - 1]["text"] == "-":
        displacement_words = 1
        displacement = None
    else:
        displacement_words = 2
        displacement = line[power_idx - 2]["text"] + line[power_idx - 1]["text"]
    trim_end = power_idx - 1 - displacement_words  # index of the cylinder-count word
    if trim_end <= 0:
        return None
    trim = line_text(line[:trim_end]).strip()

    tail: list[dict] = []
    for word in reversed(line[power_idx + 3 :]):
        if word["text"].isdigit():
            tail.insert(0, word)
        else:
            break
    price = _last_price(tail)
    if price is None:
        return None

    if _is_electric(model):
        powertrain = "EV"
    elif _PHEV_RE.search(trim):
        powertrain = "PHEV"
    else:
        powertrain = "ICE"

    # scripts/import_scraper_data.py's powertrain_signature() dedups "the
    # same engine across trims" by stripping `trim` out of `variant_name`
    # and using what's left - for every other brand there's always some
    # engine-description text left over once the trim label is removed,
    # but here `trim` (e.g. "320d") already IS the row's entire
    # distinguishing text, so a bare f"{model} {trim}" would strip down to
    # just the model name for EVERY row in a section, collapsing all of
    # them onto one shared (and wrong) powertrain. Appending the
    # displacement/power spec - genuinely part of what makes two rows
    # "the same engine" or not - fixes that for the vast majority of rows;
    # the few pairs that share an identical spec and differ only by
    # xDrive (e.g. "320d" vs "320d xDrive" - verified against the real
    # PDF: 3 such pairs in the whole document) get an explicit "AWD"
    # marker instead, since "xDrive" itself is already part of `trim` and
    # would be stripped right back out.
    spec = f"{displacement}cm3 " if displacement else ""
    spec += f"{power}kW"
    if re.search(r"xDrive", trim):
        spec += " AWD"
    variant_name = f"{model} {trim} {spec}".strip()

    return ExtractedVariant(
        model=model,
        trim=trim,
        variant_name=variant_name,
        price=price,
        currency="CZK",
        source_page=source_page,
        raw_text=line_text(line),
        powertrain=powertrain,
    )


class BmwParser(BaseParser):
    brand = "bmw"
    powertrain = "ICE"  # nominal default; the actual powertrain is per-row/per-model, see _is_electric/_PHEV_RE

    def parse(self, pdf_path: Path) -> list[ExtractedVariant]:
        """See module docstring for the section/row format and how the
        two trailing prices are told apart.

        Args:
            pdf_path: Local path to the downloaded combined BMW price-list PDF.

        Returns:
            One `ExtractedVariant` per data row found across every page,
            `model` set from that row's own section heading and
            `powertrain` classified per row/section.
        """
        variants: list[ExtractedVariant] = []

        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                model: str | None = None
                for line in group_into_lines(page.extract_words()):
                    text = line_text(line)
                    section_model = _extract_model(text)
                    if section_model is not None:
                        model = section_model
                        continue
                    if model is None:
                        continue
                    variant = _parse_row(line, model, page.page_number)
                    if variant is not None:
                        variants.append(variant)

        return variants

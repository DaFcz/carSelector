"""Common interface for all per-OEM price list/equipment parsers.

Every brand has its own PDF layout (or, for Audi alone, a JSON API
response instead of a PDF - see `parsers/audi.py`'s own module
docstring), so instead of one universal parser there's a single
`BaseParser` and per-OEM implementations. If a brand has structurally
different lineups (e.g. Škoda: combustion models vs. EVs have a
completely different table), they get their own parser (skoda_ice.py,
skoda_ev.py) instead of branching inside one — see
doc/arch/webScraping/IMPLEMENTATION_PLAN.md.

A new brand/lineup = a new file in this directory + registration in
config/sources.yaml (parser_key), nothing else needs to change.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

# "ICE" (internal combustion engine) or "EV" (electric vehicle) — this
# field makes it possible to filter variants across brands without
# separate database tables.
Powertrain = str


@dataclass
class ExtractedVariant:
    """A single extracted row (vehicle variant) with a link back to the source for verification."""

    model: str
    trim: str | None
    variant_name: str
    price: float | None
    currency: str
    source_page: int
    raw_text: str  # exact text/table row from the PDF — for manual verification
    powertrain: Powertrain
    equipment: dict[str, str] = field(default_factory=dict)  # name -> STANDARD/OPTIONAL/...
    # name -> price in CZK, for items whose price the parser could read (see
    # e.g. skoda_equipment.parse_standalone_equipment) - only meaningful for
    # names that also appear in `equipment`; not every brand's parser fills
    # this in yet.
    equipment_surcharge: dict[str, float] = field(default_factory=dict)


class BaseParser:
    """Parser interface. `parse` must return a list of ExtractedVariant so
    every record can be traced back to its page and raw text in the PDF (verification)."""

    brand: str
    powertrain: Powertrain

    def parse(self, pdf_path: Path) -> list[ExtractedVariant]:
        """Extracts every vehicle variant (price, trim, engine, equipment
        where available) from one downloaded price-list PDF.

        Args:
            pdf_path: Local path to the downloaded document, as returned
                by `downloaders.pdf_downloader.PdfDownloader.download`
                (or, for Audi alone, `downloaders.json_downloader
                .JsonDownloader.download`).

        Returns:
            One `ExtractedVariant` per vehicle variant/trim/powertrain
            combination found in the document. Each must carry the
            `source_page` and `raw_text` it was read from, so it can be
            verified against the source (see `verification/review_cli.py`).

        Raises:
            NotImplementedError: Always, on the base class - every
                concrete parser must override this.
        """
        raise NotImplementedError

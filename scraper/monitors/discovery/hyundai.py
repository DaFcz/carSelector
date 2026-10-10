"""Discoverer for hyundai.com/cz.

Unlike Škoda/Kia (one shared listing page) and like Volkswagen, Hyundai has
a separate page per model at `/cz/modely/<slug>.html` — but unlike VW, the
slug can't be derived from the model name at all (marketing prefixes vary:
"nova-i20", "nova-i30", "nova-kona", "novy-tucson", "nove-santa-fe"), so
`_SLUG_OVERRIDES` is required for every model, not just the exceptions.
The page is server-rendered; the price-list link is a plain `<a
class="downloadlist__link" href="...">` with the href read directly
(2026-08-28), no JSON attribute parsing needed. The link's OWN text
(`a.get_text()`) isn't usable for matching, though - it concatenates every
descendant text node, including the file-type/size badge that follows the
title in the DOM ("... l Ceník PDF 1.16 MB download_new"); the title alone
is a dedicated `<span class="downloadlist__main-text">` inside the anchor.

A model page lists several "Ceník" (price list) documents for different
purposes, not just one:
- "Akční ceník" (campaign/promotional price list) and "Ceník příslušenství"
  (accessories) are different document TYPES, not the current price list —
  skipped by requiring the link text to end with exactly "l Ceník" (the
  promotional one ends with "l Akční ceník", the accessories one with
  "l Ceník příslušenství").
- The remaining "l Ceník" links differ by model year, e.g. "TUCSON MR27
  (pouze pro nové objednávky do výroby) l Ceník" (current) vs "TUCSON MR26
  (skladové vozy) l Ceník" (previous year, stock only) — `_model_year` picks
  the highest "MRxx" found (a range like "MR26-27" counts as the second
  number), same principle as Kia's "Ceník" -> "Ceník skladových vozidel"
  fallback: prefer the current one.
- Tucson additionally splits into two entirely separate documents by
  powertrain line ("TUCSON MR27 ... l Ceník" for ICE/MHEV, "TUCSON Hybrid
  a Plug-in MR27 ... l Ceník" for HEV/PHEV) — both are discovered, the
  Hybrid one returned under a distinct "<model> Hybrid" key, same principle
  as Kia's "Sportage"/"Sportage HEV" split (see monitors/discovery/kia.py).
  Santa Fe's price list is HEV/PHEV-only but its link text has no "Hybrid"
  marker, so it's discovered as a single plain document — HyundaiParser
  classifies HEV vs PHEV per row regardless (same as VW's mixed-powertrain
  documents), so this split only matters when it's genuinely two separate
  PDFs to fetch.

Some models (e.g. Bayon) currently have no discoverable "l Ceník" link at
all (verified 2026-08-28) — `discover` simply omits them, same as VW's
Touareg precedent.
"""

from __future__ import annotations

import re

import requests
from bs4 import BeautifulSoup

from scraper.sources.registry import Source

from .base import BaseDiscoverer

_BASE_URL = "https://www.hyundai.com"
_SLUG_OVERRIDES = {
    "i20": "nova-i20",
    "i30": "nova-i30",
    "Kona": "nova-kona",
    "Tucson": "novy-tucson",
    "Santa Fe": "nove-santa-fe",
}
_MODEL_YEAR_RE = re.compile(r"MR(\d+)(?:-(\d+))?")


def _model_year(text: str) -> int:
    """Returns the highest two-digit model year found in `text` (e.g. 27
    for both "MR27" and the range "MR26-27"), or -1 if none is found (so
    a link without a recognizable model year sorts last, never chosen over
    one that has it)."""
    match = _MODEL_YEAR_RE.search(text)
    if not match:
        return -1
    first, second = match.groups()
    return int(second) if second else int(first)


class HyundaiDiscoverer(BaseDiscoverer):
    def discover(self, source: Source, *, timeout: int = 30) -> dict[str, str]:
        """Args:
            source: Registry entry giving the models to discover - like
                Volkswagen, Hyundai has a separate price-list page fetched
                per model (see module docstring for the slug mapping).
            timeout: HTTP request timeout in seconds, applied per model
                page fetched.

        Returns:
            `{model: price_list_url}` for each of `source.models` whose
            page has a current "l Ceník" link - a model with no page, or
            no such link on it, is simply omitted. Tucson-style dual
            powertrain-line documents add a second `"<model> Hybrid"` key.
        """
        found: dict[str, str] = {}

        for model in source.models:
            slug = _SLUG_OVERRIDES.get(model)
            if slug is None:
                continue
            page_url = f"{_BASE_URL}/cz/modely/{slug}.html"

            response = requests.get(page_url, timeout=timeout)
            if response.status_code != 200:
                continue

            soup = BeautifulSoup(response.text, "html.parser")
            candidates = []
            for a in soup.find_all("a", class_="downloadlist__link"):
                title = a.find("span", class_="downloadlist__main-text")
                if title is not None and a.get("href"):
                    candidates.append((title.get_text(strip=True), a["href"]))
            price_list_candidates = [(text, href) for text, href in candidates if text.endswith("l Ceník")]

            plain = [c for c in price_list_candidates if "Hybrid" not in c[0]]
            hybrid = [c for c in price_list_candidates if "Hybrid" in c[0]]

            if plain:
                found[model] = max(plain, key=lambda c: _model_year(c[0]))[1]
            if hybrid:
                found[f"{model} Hybrid"] = max(hybrid, key=lambda c: _model_year(c[0]))[1]

        return found

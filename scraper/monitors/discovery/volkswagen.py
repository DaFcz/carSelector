"""Discoverer for volkswagen.cz.

Unlike Škoda, VW doesn't have a single listing page with all models —
each model has its own price list page at `/<slug>/<slug>/ceniky`
(verified for all 11 combustion models — returned HTTP 200 on
2026-07-19, see `source.models` in `sources.yaml`). The page is built on
React/Next.js, but the PDF links (`data-gtm-element-url`) are present
directly in the initial HTML (server-rendered), so requests +
BeautifulSoup is enough, Playwright isn't needed.

PDF links have `data-gtm-element="infomaterial_download"` and anchor
text starting with "Ceník modelu <Model>" ("Price list for model
<Model>") for the main price list. But the text is NOT consistent across
models — some have the file size appended after the name ("Ceník modelu
Polo (5,1 MB)"), T-Roc additionally has the marketing word "Nový" ("New")
("Ceník modelu Nový T-Roc (16,6 MB)") — so an exact string match isn't
enough, see `_is_main_price_list`. Special editions/variants ("Ceník
modelu Golf GTI", "Ceník modelu Golf Variant R", "Akční ceník modelu ...")
are skipped the same way Škoda skips catalogs/accessories — for those,
the candidate name (after stripping the size/"Nový") has more words than
the plain model name, so it doesn't match.

Some models (e.g. Touareg — on 2026-07-19 only "Ceník akčního modelu
Touareg Final Edition", no regular price list) may not have a main price
list at a given moment — discover then simply omits that model, which
isn't an error.

EVs (ID.) have two further irregularities:
- the anchor text omits the word "modelu" for newer models ("Ceník ID.3
  Neo", "Ceník ID. Polo (1,7 MB)" instead of "Ceník modelu ..."), hence
  `_PRICE_LIST_PREFIXES` tries both variants.
- the URL slug can't be derived from the model name the way it can for
  combustion models (the period in "ID.3"/"ID.4"/"ID.7" isn't in the
  slug: .../id4/..., and "ID.3" currently only has a page at "id3-neo",
  not "id3") — `_SLUG_OVERRIDES`."""

from __future__ import annotations

import re

import requests
from bs4 import BeautifulSoup

from scraper.sources.registry import Source

from .base import BaseDiscoverer

_BASE_URL = "https://www.volkswagen.cz"
_PRICE_LIST_PREFIXES = ("Ceník modelu ", "Ceník ")
_TRAILING_SIZE_RE = re.compile(r"\s*\([\d,]+\s*[MK]B\)\s*$")
_SLUG_OVERRIDES = {
    "ID.3 Neo": "id3-neo",
    "ID.4": "id4",
    "ID.7": "id7",
    "ID.7 Tourer": "id7-tourer",
    "ID. Polo": "id-polo",
}


def _is_main_price_list(anchor_text: str, model: str) -> bool:
    for prefix in _PRICE_LIST_PREFIXES:
        if not anchor_text.startswith(prefix):
            continue
        candidate = _TRAILING_SIZE_RE.sub("", anchor_text[len(prefix) :]).strip()
        candidate = candidate.removeprefix("Nový ").strip()
        if candidate == model:
            return True
    return False


class VolkswagenDiscoverer(BaseDiscoverer):
    def discover(self, source: Source, *, timeout: int = 30) -> dict[str, str]:
        """Args:
            source: Registry entry giving the models to discover - unlike
                Škoda/Kia (one shared listing page), VW has a separate
                price-list page fetched per model (see module docstring).
            timeout: HTTP request timeout in seconds, applied per model
                page fetched.

        Returns:
            `{model: price_list_url}` for each of `source.models` whose
            page returned a link (a model with no page, or no matching
            link on it, is simply omitted).
        """
        found: dict[str, str] = {}

        for model in source.models:
            slug = _SLUG_OVERRIDES.get(model, model.lower().replace(" ", "-"))
            page_url = f"{_BASE_URL}/{slug}/{slug}/ceniky"

            response = requests.get(page_url, timeout=timeout)
            if response.status_code != 200:
                continue

            soup = BeautifulSoup(response.text, "html.parser")
            anchor = next(
                (
                    a
                    for a in soup.find_all("a", attrs={"data-gtm-element": "infomaterial_download"})
                    if _is_main_price_list(a.get_text(strip=True), model)
                ),
                None,
            )
            if anchor is None:
                continue

            relative_url = anchor.get("data-gtm-element-url")
            if relative_url:
                found[model] = f"{_BASE_URL}{relative_url}"

        return found

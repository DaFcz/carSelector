"""Discoverer for skoda-auto.cz.

Škoda renders links as `<a href=".../_doc/<uuid>">Model - Ceník</a>`
("Ceník" = "Price list"; instead of a regular space around the dash it's
often `&nbsp;`, and sometimes the same document is linked by multiple
anchor tags — one with text, one empty/image-only). BeautifulSoup
handles both the entities and the duplicates without needing a custom
regex on the raw HTML (that was tried first and was unreliable).
"""

from __future__ import annotations

import requests
from bs4 import BeautifulSoup

from scraper.sources.registry import Source

from .base import BaseDiscoverer

_PRICE_LIST_LABEL = "Ceník"


class SkodaDiscoverer(BaseDiscoverer):
    def discover(self, source: Source, *, timeout: int = 30) -> dict[str, str]:
        """Args:
            source: Registry entry giving Škoda's single listing page URL
                (this discoverer is registered for both the skoda_ice and
                skoda_ev parser_keys - see monitors/discovery/registry.py)
                and the models to look for on it.
            timeout: HTTP request timeout in seconds.

        Returns:
            `{model: price_list_url}` for each of `source.models` found
            on the listing page.
        """
        response = requests.get(source.source_url, timeout=timeout)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        found: dict[str, str] = {}

        for anchor in soup.find_all("a", href=True):
            href = anchor["href"]
            if "/_doc/" not in href:
                continue

            text = anchor.get_text(strip=True).replace("\xa0", " ")
            if not text or " - " not in text:
                continue

            model, _, doc_type = text.partition(" - ")
            model = model.strip()
            doc_type = doc_type.strip()

            if doc_type != _PRICE_LIST_LABEL or model not in source.models:
                continue

            found.setdefault(model, href)  # keep the first one if the same document is linked twice

        return found

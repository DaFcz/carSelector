"""Discoverer for kia.com/cz/prodej/ceniky-katalogy/.

Like Škoda (a single listing page with all models) and unlike VW (a
separate page per model). The page is an HTML table with one <tr> per
model: the model name is in a `<div class="modeltitle">` cell, and the
price list link is in that row's `<td data-label="Ceník">` cell — both
verified against the real page 2026-08-13.

Some models (e.g. Ceed SW) have no current "Ceník" (an empty placeholder
icon instead) — their only price list lives under "Ceník skladových
vozidel" ("stock vehicle price list"), which is used as a fallback.

Some models are split across multiple rows by powertrain, e.g. "Nová
Sportage" (ICE) / "Nová Sportage HEV" / "Nová Sportage PHEV" — the ICE
and HEV/PHEV variants are genuinely different PDF documents (see
parsers/kia.py), so both the base row and the "... HEV" row are
discovered, returned under distinct keys ("Sportage" / "Sportage HEV").
The "... PHEV" row links to the exact same document as the "... HEV" row
for the same model, so it's skipped — processing it too would just be a
redundant (harmless, SourceMonitor dedups by content hash) second key
pointing at the same URL.
"""

from __future__ import annotations

import requests
from bs4 import BeautifulSoup

from scraper.sources.registry import Source

from .base import BaseDiscoverer

_MARKETING_PREFIXES = ("Nový ", "Nová ", "Nové ", "Kia ")
_PRICE_LIST_LABELS = ("Ceník", "Ceník skladových vozidel")  # fallback order


def _strip_marketing_prefix(title: str) -> str:
    for prefix in _MARKETING_PREFIXES:
        if title.startswith(prefix):
            return title.removeprefix(prefix)
    return title


class KiaDiscoverer(BaseDiscoverer):
    def discover(self, source: Source, *, timeout: int = 30) -> dict[str, str]:
        """Args:
            source: Registry entry giving Kia's single listing page URL
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

        for row in soup.find_all("tr"):
            title_div = row.find("div", class_="modeltitle")
            if title_div is None:
                continue

            card_title = _strip_marketing_prefix(title_div.get_text(strip=True))
            if card_title.endswith(" PHEV"):
                continue  # same document as the "... HEV" row, see module docstring

            base_model = card_title.removesuffix(" HEV")
            if base_model not in source.models:
                continue

            pdf_url = None
            for label in _PRICE_LIST_LABELS:
                cell = row.find("td", attrs={"data-label": label})
                anchor = cell.find("a", href=True) if cell else None
                if anchor is not None:
                    pdf_url = anchor["href"]
                    break

            if pdf_url:
                found[card_title] = pdf_url

        return found

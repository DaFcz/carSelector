"""Discoverer for renault.cz.

Like Dacia (its own Renault Group sibling, sharing the same
`cdn.group.renault.com` CDN - just `/ren/` instead of `/dac/`), a single
listing page (https://www.renault.cz/ceniky-a-brozury.html) is server-
rendered with each model's own "Ceník" link as a plain `<a href="...pdf">`
- verified 2026-09-12, no browser needed.

Renault's own current CZ lineup is considerably larger than Dacia's,
though: alongside the combustion/hybrid personal cars (Clio, Captur,
Symbioz, Arkana, Austral, Espace, Rafale), it now also sells five
"e-tech elektrický" (electric-only) personal cars under revived nameplates
(Twingo, Renault 4, Renault 5, Megane, Scenic) - each with its own
`<slug>-e-tech-elektricky-cenik.pdf` link on the very same page, alongside
Renault's commercial-vehicle lineup (Kangoo, Trafic, Master and their own
electric versions) that `_SLUG_MODELS` simply omits, same "personal cars
only" scope as every other brand here."""

from __future__ import annotations

import re

import requests

from scraper.sources.registry import Source

from .base import BaseDiscoverer

_BASE_URL = "https://www.renault.cz"
_CENIKY_PAGE = f"{_BASE_URL}/ceniky-a-brozury.html"
_PRICE_LIST_RE = re.compile(
    r'href="(https://cdn\.group\.renault\.com/ren/cz/pdf/pricelists/([a-z0-9-]+)-cenik\.pdf\.asset\.pdf/[a-f0-9]+\.pdf)"'
)
_SLUG_MODELS = {
    "clio": "Clio",
    "captur": "Captur",
    "symbioz": "Symbioz",
    "arkana": "Arkana",
    "austral": "Austral",
    "espace": "Espace",
    "rafale": "Rafale",
    "twingo-e-tech-elektricky": "Twingo",
    "renault-4-e-tech-elektricky": "4",
    "renault-5-e-tech-elektricky": "5",
    "megane-e-tech-elektricky": "Megane",
    "scenic-e-tech-elektricky": "Scenic",
}


class RenaultDiscoverer(BaseDiscoverer):
    def discover(self, source: Source, *, timeout: int = 30) -> dict[str, str]:
        """Args:
            source: Registry entry for the renault source (only
                `_CENIKY_PAGE` is fetched - see module docstring).
            timeout: HTTP request timeout in seconds.

        Returns:
            `{model: price_list_url}` for each of `source.models` whose
            "Ceník" link was found on the listing page - a model with no
            matching slug is simply omitted.
        """
        response = requests.get(_CENIKY_PAGE, timeout=timeout)
        if response.status_code != 200:
            return {}

        found: dict[str, str] = {}
        for url, slug in _PRICE_LIST_RE.findall(response.text):
            model = _SLUG_MODELS.get(slug)
            if model is None or model not in source.models:
                continue
            found[model] = url

        return found

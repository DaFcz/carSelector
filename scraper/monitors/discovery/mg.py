"""Discoverer for mgmotor-czech.cz.

Unlike Opel/Peugeot, MG's own site has no bot-blocking at all - verified
2026-09-13, `requests` gets a plain 200 for the homepage and every PDF
link on it. The homepage itself (not a separate "ceníky" page - there
isn't one) links every current model's own "Ceník" PDF directly, same
"single listing page" shape as Škoda/BMW/Dacia's own discoverers, just
with the price-list links scattered across several per-model sections of
one page rather than gathered under one heading.

`_FILENAME_MODELS` maps each PDF's own basename (the href, with or
without a leading "/", trimmed to its last path segment - the homepage
prints the same MG3 link both ways in different sections, verified
2026-09-13) to the model name `MgParser`'s own cover-page extraction
would produce for that document, so `source.models` can filter on the
same names the parser uses without the discoverer having to open every
PDF itself just to find out what's inside."""

from __future__ import annotations

import re
from urllib.parse import urljoin

import requests

from scraper.sources.registry import Source

from .base import BaseDiscoverer

_BASE_URL = "https://www.mgmotor-czech.cz"
_PDF_LINK_RE = re.compile(r'href="([^"]*[Cc]enik[^"]*\.pdf)"')
_FILENAME_MODELS = {
    "cenik_MG3_CZ.pdf": "3",
    "MGS9-PHEV_cenik.pdf": "S9 PHEV",
    "cenik_nove_ZS_CZ.pdf": "ZS",
    "cenik_zcela_nove_HS_CZ.pdf": "HS",
    "Cenik-Zcela-nove-MG4-EV-Urban-Urban.pdf": "4 EV Urban",
    "MGS5-EV_cenik.pdf": "S5 EV",
    "cenikCZCyberster.pdf": "Cyberster",
}


class MgDiscoverer(BaseDiscoverer):
    def discover(self, source: Source, *, timeout: int = 30) -> dict[str, str]:
        """Args:
            source: Registry entry for the mg source (only the homepage is
                fetched - see module docstring).
            timeout: HTTP request timeout in seconds.

        Returns:
            `{model: price_list_url}` for each of `source.models` whose
            own "Ceník" link was found on the homepage - a model with no
            matching link is simply omitted.
        """
        response = requests.get(_BASE_URL, timeout=timeout)
        if response.status_code != 200:
            return {}

        found: dict[str, str] = {}
        for href in _PDF_LINK_RE.findall(response.text):
            filename = href.rsplit("/", 1)[-1]
            model = _FILENAME_MODELS.get(filename)
            if model is None or model not in source.models or model in found:
                continue
            found[model] = urljoin(_BASE_URL, href)

        return found

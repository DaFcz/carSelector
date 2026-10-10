"""Discoverer for cupraofficial.cz.

Like Škoda/BMW/Dacia, a single listing page
(https://www.cupraofficial.cz/nabidky/ceniky-a-katalogy, "Ceníky a
katalogy") lists every model's price list - verified 2026-09-12, server-
rendered (`requests` sees the same markup a browser does, no Playwright
needed). Unlike any of those three, the actual "Stáhnout"-equivalent link
isn't a plain `<a href="...pdf">` at all: `href="#"` (a client-side
download handler), with the real path only present in a
`data-gtm-element-url` attribute (no ".pdf" suffix, but the server returns
`Content-Type: application/pdf` regardless - verified by fetching it
directly) - and the MODEL itself is identified by a sibling
`data-gtm-event="Ceniky_a_katalogy-Stahnout_cenik_<Slug>"` attribute on the
same `<a>`, not by anchor text or nearby headings (both of which just read
"Ceník" for every model alike). `_CENIK_LINK_RE` captures both attributes
from one tag in a single pass.

The page also lists a "Katalogy CUPRA" section (brochures, own
`data-gtm-event` prefix "Ceniky_a_katalogy-Stahnout_katalog_...") and a
"CUPRA CONNECT" one (infotainment manuals) - `_CENIK_LINK_RE` only matches
the "Stahnout_cenik_" prefix, so neither is picked up.

CUPRA's full current CZ lineup is 8 nameplates, but only 6 have a price
list of their own here: Ateca is sold as stock-only (no "CENÍK" link on
this page for it, only a "Katalog" - matches the homepage's own "SKLADOVÉ
VOZY" label instead of a price link) and Tavascan has no price-list link
yet either (too new - CZ sales hadn't started as of this verification
date). `_SLUG_MODELS` covers exactly the 6 that do."""

from __future__ import annotations

import re

import requests

from scraper.sources.registry import Source

from .base import BaseDiscoverer

_BASE_URL = "https://www.cupraofficial.cz"
_CENIKY_PAGE = f"{_BASE_URL}/nabidky/ceniky-a-katalogy"
_CENIK_LINK_RE = re.compile(
    r'<a[^>]*data-gtm-event="Ceniky_a_katalogy-Stahnout_cenik_([A-Za-z_]+)"[^>]*'
    r'data-gtm-element-url="([^"]+)"[^>]*>',
    re.IGNORECASE,
)
_SLUG_MODELS = {
    "Leon": "Leon",
    "Leon_sportstourer": "Leon Sportstourer",
    "Formentor": "Formentor",
    "Terramar": "Terramar",
    "Born": "Born",
    "Raval": "Raval",
}


class CupraDiscoverer(BaseDiscoverer):
    def discover(self, source: Source, *, timeout: int = 30) -> dict[str, str]:
        """Args:
            source: Registry entry giving the models to discover (only
                `_CENIKY_PAGE` is fetched - see module docstring).
            timeout: HTTP request timeout in seconds.

        Returns:
            `{model: price_list_url}` for each of `source.models` whose
            "Ceník" link was found on the listing page - a model with no
            matching slug on the page is simply omitted.
        """
        response = requests.get(_CENIKY_PAGE, timeout=timeout)
        if response.status_code != 200:
            return {}

        found: dict[str, str] = {}
        for slug, path in _CENIK_LINK_RE.findall(response.text):
            model = _SLUG_MODELS.get(slug)
            if model is None or model not in source.models:
                continue
            found[model] = _BASE_URL + path

        return found

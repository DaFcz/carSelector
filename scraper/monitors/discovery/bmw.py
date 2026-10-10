"""Discoverer for bmw.cz.

Like Škoda, and unlike every other brand added after it, this is about as
simple as discovery gets: `https://www.bmw.cz/cs/topics/details/katalogy-
ceniky-ke-stazeni.html` ("Katalogy a ceníky ke stažení") is server-rendered
with the combined "Ceník základních modelů" ("Price list of base models" -
covers the entire current lineup, see parsers/bmw.py) as a plain `<a
href="...pdf">` link, no JSON-in-a-script-tag or client-rendered widget to
work around (verified 2026-08-29 - a previous note in config/sources.yaml
recorded this page as unreachable from this environment; that's no longer
the case). The href is a relative, already-URL-encoded path
(`/content/dam/bmw/...pdf`), so only the domain needs prefixing - no
`urllib.parse.quote` step like Mercedes-Benz's needs.

The page also links a couple of older, narrower price lists further down
(an M3/M4-only one from 2023, seemingly superseded by the combined one
having its own current M3/M4 rows) - `_PRICE_LIST_RE` only matches an href
whose filename contains "Cenik" (this brand's own spelling, capital C) to
avoid picking one of those up instead."""

from __future__ import annotations

import re

import requests

from scraper.sources.registry import Source

from .base import BaseDiscoverer

_BASE_URL = "https://www.bmw.cz"
_CENIKY_PAGE = f"{_BASE_URL}/cs/topics/details/katalogy-ceniky-ke-stazeni.html"
_PRICE_LIST_RE = re.compile(r'href="(/content/dam/bmw/[^"]*Cenik[^"]*\.pdf)"')


class BmwDiscoverer(BaseDiscoverer):
    def discover(self, source: Source, *, timeout: int = 30) -> dict[str, str]:
        """Args:
            source: Registry entry for the bmw source (only `_CENIKY_PAGE`
                is fetched - `source.models`/`source_url` aren't otherwise
                used, see module docstring for why one fetch is enough).
            timeout: HTTP request timeout in seconds.

        Returns:
            `{"all": price_list_url}` - a single entry, since one PDF
            covers every model (empty dict if the page couldn't be
            fetched or no matching document was found on it).
        """
        response = requests.get(_CENIKY_PAGE, timeout=timeout)
        if response.status_code != 200:
            return {}

        match = _PRICE_LIST_RE.search(response.text)
        if match is None:
            return {}

        return {"all": _BASE_URL + match.group(1)}

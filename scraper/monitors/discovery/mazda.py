"""Discoverer for mazda.cz.

Like Škoda, there's a single listing page with all models
(`https://www.mazda.cz/formulae/cenik/`, "Přehled všech ceníků a brožur
modelů Mazda") — but unlike Škoda, the page is a client-rendered app (React/
similar) whose visible DOM has no plain `<a href="...pdf">` (verified
2026-08-29: every "Stáhnout" control is a `<button>` with no href or data
attribute pointing at a file). The actual PDF links ARE present server-side
though, inlined as a big JSON blob assigned to a page-data variable inside a
`<script>` tag - one object per model, shaped roughly like:

    {"caption":"MAZDA CX-5 ","...","downloads":[{"title":"Akční ceník
    Mazda CX-5","cta":{"text":"Stáhnout","link":"https://media-assets.
    mazda.eu/raw/upload//mazdacz/globalassets/pdfs/akcni_2026_07/
    mazda_cx-5_akcni_cenik_2026-07_cz.pdf?rnd=49ef03", ...}}], ...}

`discover` reads `"caption":"..."` markers directly out of the raw HTML
(same "read JSON out of a script tag with regex" approach as Mercedes-Benz,
see monitors/discovery/mercedes_benz.py) and, for each one matching a
model this scraper tracks, takes the first `"link":"...pdf..."` found
before the next caption. A model with two documents (e.g. Mazda3's current
price list plus a separate "Akční ceník - skladové vozy", stock-only,
price list) only ever yields the FIRST/current one this way - the same
"prefer the current document" precedent as Toyota (see monitors/discovery/
toyota.py's module docstring).

Unlike every other brand's link, this one doesn't need URL-encoding before
the GET (verified 2026-08-29: the path is plain ASCII, no diacritics)."""

from __future__ import annotations

import re

import requests

from scraper.sources.registry import Source

from .base import BaseDiscoverer

_CENIKY_PAGE = "https://www.mazda.cz/formulae/cenik/"
_CAPTION_RE = re.compile(r'"caption":"([^"]*?)\s*"')
_LINK_RE = re.compile(r'"link":"(https://media-assets\.mazda\.eu/[^"]+\.pdf[^"]*)"')
# caption (as it appears on the page, always "MAZDA <model>") -> canonical model name
_MODEL_CAPTIONS = {
    "MAZDA CX-5": "CX-5",
    "MAZDA3": "3",
    "MAZDA CX-30": "CX-30",
}


class MazdaDiscoverer(BaseDiscoverer):
    def discover(self, source: Source, *, timeout: int = 30) -> dict[str, str]:
        """Args:
            source: Registry entry giving the models to discover (only
                `_CENIKY_PAGE` is fetched - see module docstring).
            timeout: HTTP request timeout in seconds.

        Returns:
            `{model: price_list_url}` for each of `source.models` whose
            caption block on the listing page has a PDF link - a model
            with no matching caption, or a caption with no link, is
            simply omitted.
        """
        response = requests.get(_CENIKY_PAGE, timeout=timeout)
        if response.status_code != 200:
            return {}

        text = response.text
        captions = list(_CAPTION_RE.finditer(text))

        found: dict[str, str] = {}
        for i, match in enumerate(captions):
            model = _MODEL_CAPTIONS.get(match.group(1).strip())
            if model is None or model not in source.models:
                continue
            end = captions[i + 1].start() if i + 1 < len(captions) else len(text)
            link_match = _LINK_RE.search(text, match.end(), end)
            if link_match is not None:
                found[model] = link_match.group(1)

        return found

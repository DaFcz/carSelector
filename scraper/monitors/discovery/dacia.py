"""Discoverer for dacia.cz.

Like Škoda/BMW, a single listing page (https://www.dacia.cz/ceniky-a-
brozury.html, "Ceníky, brožury, pdf") is server-rendered with each model's
own "Ceník" link as a plain `<a href="...pdf">` — verified 2026-09-07.
Unlike either of those, the href points at Renault Group's shared asset CDN
(cdn.group.renault.com), not dacia.cz itself, and the filename embeds the
model as a slug (`pricelists/<slug>-cenik.pdf.asset.pdf/<hash>.pdf`, e.g.
".../pricelists/sandero-stepway-cenik.pdf.asset.pdf/09902ceec3.pdf") -
`_SLUG_MODELS` maps each slug back to its canonical model name (can't be
derived mechanically - the slug replaces the model's own space with a
hyphen, and there's no other reliable signal on the page to read the name
from, see parsers/dacia.py's own note on the page's inconsistent heading
casing).

The page currently lists 6 models (Spring, Sandero, Sandero Stepway,
Jogger, Duster, Bigster) - the full current CZ lineup (Logan/Lodgy et al.
are no longer sold new, so `sources.yaml`'s `models` list only names these
six). Each model has exactly one "Ceník" link (no separate trim/powertrain
documents like Kia's Sportage, no stock/promo duplicate like Mazda's), so,
unlike Mazda's caption-scoped search, one page-wide regex sweep is enough -
order on the page doesn't matter since the slug identifies the model
directly."""

from __future__ import annotations

import re

import requests

from scraper.sources.registry import Source

from .base import BaseDiscoverer

_CENIKY_PAGE = "https://www.dacia.cz/ceniky-a-brozury.html"
_PRICE_LIST_RE = re.compile(
    r'href="(https://cdn\.group\.renault\.com/dac/cz/pdf/pricelists/'
    r'([a-z-]+)-cenik\.pdf\.asset\.pdf/[a-f0-9]+\.pdf)"'
)
_SLUG_MODELS = {
    "spring": "Spring",
    "sandero": "Sandero",
    "sandero-stepway": "Sandero Stepway",
    "jogger": "Jogger",
    "duster": "Duster",
    "bigster": "Bigster",
}


class DaciaDiscoverer(BaseDiscoverer):
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
        for url, slug in _PRICE_LIST_RE.findall(response.text):
            model = _SLUG_MODELS.get(slug)
            if model is None or model not in source.models:
                continue
            found[model] = url

        return found

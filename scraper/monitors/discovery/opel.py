"""Discoverer for opel.cz.

Unlike every other brand here, this one can't actually discover anything
automatically: opel.cz's listing page
(https://www.opel.cz/nastroje/katalogy-a-ceniky.html) sits behind an
Akamai WAF that blocks `requests` at the TLS/network-fingerprint level,
not just on missing headers - verified 2026-09-12 that even a complete,
realistic browser header set (the same one that DOES get through for the
PDF endpoints themselves, see `pdf_downloader.py`'s own `_BROWSER_HEADERS`)
still gets rejected for the listing page and even the bare homepage. Only
a real browser engine (e.g. Playwright) could render that page, which is
out of scope here (see `pdf_downloader.py`'s own docstring and this
brand's sources.yaml entry for the same note).

So `_DOCUMENT_URLS` hardcodes the current URLs directly instead of finding
them on a page - the same 11 URLs `scripts/download_opel_pricelists.py`
uses to seed this brand's own test fixtures (that script exists for
exactly this reason: these URLs can't be found programmatically, so a
human has to). Each of Opel's 6 personal-car nameplates has its own
combustion/hybrid document (Astra has two - "HB" hatchback and "ST"
Sports Tourer wagon, sharing one Astra Electric document between them
instead of splitting it too) plus its own separate all-electric document
- 11 keys total, one per real document (not one per real-world model:
Astra alone needs 3 different keys/URLs to reach all of its own price
data) - see OpelParser's own module docstring for why the *parsed*
`model` field then normalizes 3 of these keys down to plain "Astra".

The URL path itself embeds a quarter marker ("2026/Q2") that will
presumably roll over every quarter - when these URLs eventually 404,
someone has to visit the listing page in a real browser, copy the new
links, and update `_DOCUMENT_URLS` by hand; there's no way to detect that
automatically short of building the browser-based discovery this module's
docstring says is out of scope."""

from __future__ import annotations

from scraper.sources.registry import Source

from .base import BaseDiscoverer

_BASE_URL = "https://www.opel.cz/content/dam/opel/czech_republic/brochure-library/pricelists/2026/Q2"

# document key (as listed in this source's own `models` in sources.yaml) ->
# source filename under _BASE_URL. Combo/Vivaro/Movano commercial vehicles
# have their own price lists on the same listing page but are out of
# scope, same convention as every other brand here.
_DOCUMENT_URLS = {
    "Corsa": f"{_BASE_URL}/CZ_Corsa.pdf",
    "Corsa Electric": f"{_BASE_URL}/CZ_Corsa_Electric.pdf",
    "Astra HB": f"{_BASE_URL}/CZ_Astra_HB.pdf",
    "Astra ST": f"{_BASE_URL}/CZ_Astra_ST.pdf",
    "Astra Electric": f"{_BASE_URL}/CZ_Astra_Electric.pdf",
    "Mokka": f"{_BASE_URL}/CZ_Mokka.pdf",
    "Mokka Electric": f"{_BASE_URL}/CZ_Mokka_Electric.pdf",
    "Frontera": f"{_BASE_URL}/CZ_Frontera.pdf",
    "Frontera Electric": f"{_BASE_URL}/CZ_Frontera_Electric.pdf",
    "Grandland": f"{_BASE_URL}/CZ_Grandland.pdf",
    "Grandland Electric": f"{_BASE_URL}/CZ_Grandland_Electric.pdf",
}


class OpelDiscoverer(BaseDiscoverer):
    def discover(self, source: Source) -> dict[str, str]:
        """Args:
            source: Registry entry for the opel source - only
                `source.models` is used, to filter `_DOCUMENT_URLS` down
                to whichever document keys this source is configured for
                (see module docstring for why there's no HTTP request
                here at all, unlike every other discoverer).

        Returns:
            `{document_key: price_list_url}` for each of `source.models`
            found in `_DOCUMENT_URLS` - a model with no matching entry is
            simply omitted, same convention as every other discoverer.
        """
        return {key: url for key, url in _DOCUMENT_URLS.items() if key in source.models}

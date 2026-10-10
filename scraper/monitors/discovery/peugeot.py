"""Discoverer for peugeot.cz.

Like Opel, peugeot.cz's own listing page
(https://www.peugeot.cz/uzitecne-odkazy/ceniky.html) sits behind an
Akamai WAF that blocks `requests` at the TLS/network-fingerprint level,
not just on missing headers - verified 2026-09-13 that even a complete,
realistic browser header set (the same one `pdf_downloader.py` uses for
Opel) still gets rejected, both for that page and the bare homepage.

Unlike Opel, though, the ACTUAL price-list PDFs aren't on peugeot.cz at
all - every "Ceník a tech. data" link points at peugeot.ecpaper.cz, a
separate flipbook-viewer site that embeds the real PDF (hosted on Azure
Blob Storage) in its own page. That viewer site has none of peugeot.cz's
own WAF - verified `requests` gets a plain 200 for both the viewer page
and the underlying blob URL - so `_MODEL_PAGES` hardcodes each model's own
STABLE ecpaper.cz viewer-page URL (found the same manual way Opel's own
PDF URLs were - a human visiting the blocked listing page in a real
browser), and `discover` does one `requests` GET per model to resolve
today's actual PDF URL out of that page's own HTML. This is less
stale-prone than Opel's fully-hardcoded approach: the viewer-page URLs
stay put across a routine price-list refresh (only the PDF asset
underneath changes), so only a genuine site restructuring - a new model
year's own new slug, e.g. "208-new" becoming "208-my27" - would need this
module updated by hand; a plain quarterly price refresh doesn't.

Peugeot's current CZ personal-car lineup has 9 nameplates with their own
"Ceník a tech. data" link on that listing page - `_MODEL_PAGES` covers
7 of them. The plain "308" hatchback's own link is dead (404s back to
ecpaper.cz's generic customer/catalogs page, both via `requests` and a
real browser) - only "308 SW" (the wagon) has a working document, so
plain "308" is omitted, same convention as CUPRA's own stock-only/
not-yet-on-sale omissions. Traveller's own document uses a completely
different structure PeugeotParser doesn't read yet (see that module's own
docstring), so it's omitted here too rather than left as a document this
source would find but the parser can't use. Expert/Partner/Boxer
commercial vehicles were never in `_MODEL_PAGES` to begin with, same
"personal cars only" convention as every other brand here."""

from __future__ import annotations

import re

import requests

from scraper.sources.registry import Source

from .base import BaseDiscoverer

_MODEL_PAGES = {
    "208": "https://peugeot.ecpaper.cz/osobni/208/208-new/Peugeot-208-new-cenik/?page=1",
    "2008": "https://peugeot.ecpaper.cz/osobni/2008/2008-novy-2023/Peugeot-2008-novy-2023-cenik/?page=1",
    "308 SW": "https://peugeot.ecpaper.cz/osobni/308/308-sw-new/Peugeot-308-sw-new-cenik/?page=1",
    "3008": "https://peugeot.ecpaper.cz/osobni/3008/3008-2024/Peugeot-3008-2024-cenik/?page=1",
    "408": "https://peugeot.ecpaper.cz/osobni/408/408/Peugeot-408-cenik/?page=1",
    "5008": "https://peugeot.ecpaper.cz/osobni/5008/5008-2024/Peugeot-5008-2024-cenik/?page=1",
    "Rifter": "https://peugeot.ecpaper.cz/osobni/Rifter/Rifter-2024/Peugeot-Rifter-2024-cenik/?page=1",
}
_PDF_URL_RE = re.compile(r"https://[^\"'\s]+\.pdf")


class PeugeotDiscoverer(BaseDiscoverer):
    def discover(self, source: Source, *, timeout: int = 30) -> dict[str, str]:
        """Args:
            source: Registry entry for the peugeot source - only
                `source.models` is used, to filter `_MODEL_PAGES` down to
                whichever models this source is configured for.
            timeout: HTTP request timeout in seconds, applied per model.

        Returns:
            `{model: price_list_url}` for each of `source.models` found in
            `_MODEL_PAGES` whose own ecpaper.cz viewer page was reachable
            and contained a resolvable PDF link - a model with no
            `_MODEL_PAGES` entry, an unreachable viewer page, or no
            matching PDF link is simply omitted.
        """
        found: dict[str, str] = {}
        for model, page_url in _MODEL_PAGES.items():
            if model not in source.models:
                continue

            response = requests.get(page_url, timeout=timeout)
            if response.status_code != 200:
                continue

            match = _PDF_URL_RE.search(response.text)
            if match is None:
                continue

            found[model] = match.group(0)

        return found

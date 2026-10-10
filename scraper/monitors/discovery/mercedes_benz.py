"""Discoverer for mercedes-benz.cz.

Unlike every other brand in this scraper, Mercedes-Benz doesn't have one
PDF per model at all - `https://www.mercedes-benz.cz/passengercars/services/
ceniky.html` ("Ceníky, nákupní podmínky a další dokumenty ke stažení") links
a SINGLE combined "Souhrnný ceník osobních automobilů" PDF covering the
entire current passenger-car lineup (all body styles, 74 pages, verified
2026-08-29). So `discover` doesn't need a per-model page fetch (Volkswagen/
Hyundai) or a link-text match per model (Škoda) - it just needs to find
that one document and return it once; `MercedesBenzParser` is the one that
picks the models this scraper actually cares about out of the combined PDF
(see its module docstring).

The page is an Adobe Experience Manager (AEM) app: the actual HTML has no
plain `<a href="...pdf">` tag pdfplumber's usual BeautifulSoup approach
could find (verified 2026-08-29: the rendered DOM only gets the download
links via client-side JS). The document IS present server-side, though,
inlined as a JSON payload inside a `<script>` block per download tile:

    ((window.top.aemNamespace ...).componentData ...)['<id>'] = {
        "payload": {"file": {"source": "/content/dam/czechia/pricelist-pkw/
        ceníky-2026/cenik_souhrnny_05-27-2026.pdf", ...}, ...}, ...}

so `_SOURCE_RE` reads `"source":"..."` directly out of the raw HTML rather
than parsing the DOM. The page lists 8 documents this way (the summary
price list plus various purchase-conditions/compliance PDFs) - the price
list is reliably the only one whose path contains `/pricelist-pkw/`
(the others are under `/passenger-cars/mk/downloads/` or `/brochures-pkw/`),
so that's the discriminator instead of position or link text.

The path is stored in the HTML pre-URL-encoded (raw UTF-8, e.g. an actual
"í" byte sequence, not "%C3%AD") - `urllib.parse.quote` is applied before
the GET, same as a browser would when following the link.
"""

from __future__ import annotations

import re
from urllib.parse import quote

import requests

from scraper.sources.registry import Source

from .base import BaseDiscoverer

_BASE_URL = "https://www.mercedes-benz.cz"
_CENIKY_PAGE = f"{_BASE_URL}/passengercars/services/ceniky.html"
_SOURCE_RE = re.compile(r'"source":"(/content/dam/czechia/pricelist-pkw/[^"]+\.pdf)"')


class MercedesBenzDiscoverer(BaseDiscoverer):
    def discover(self, source: Source, *, timeout: int = 30) -> dict[str, str]:
        """Args:
            source: Registry entry for the mercedes-benz source (only
                `_CENIKY_PAGE` is fetched - `source.models`/`source_url`
                aren't otherwise used, see module docstring for why one
                fetch is enough here).
            timeout: HTTP request timeout in seconds.

        Returns:
            `{"all": price_list_url}` - a single entry, since one PDF
            covers every model (empty dict if the page couldn't be
            fetched or no `/pricelist-pkw/` document was found on it).
        """
        response = requests.get(_CENIKY_PAGE, timeout=timeout)
        if response.status_code != 200:
            return {}

        match = _SOURCE_RE.search(response.text)
        if match is None:
            return {}

        return {"all": _BASE_URL + quote(match.group(1))}

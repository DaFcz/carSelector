"""Discoverer for ford.cz.

Unlike Škoda/BMW/Dacia (one shared listing page) or VW (a per-model page
whose URL is mechanically derivable from the model name), Ford's listing
page (https://www.ford.cz/pred-nakupem/dalsi-kroky/katalogy-a-ceniky-ke-
stazeni) has no PDF links of its own at all - every model's "Stáhnout"
button is an `<a href="/content/overlays/download-a-brochure-3-0/<slug>">`
that opens an AEM content-overlay fragment, and the ACTUAL PDF links only
exist on THAT fragment's own page (verified 2026-09-07 by fetching it
directly with `requests` - it's plain server-rendered HTML, no JS needed).
`<slug>` isn't derivable from the model name either (Puma's own overlay is
shared with Puma Gen-E: "puma-a-puma-gen-e") - `_MODEL_SLUGS` is the only
source of truth for it, so this discoverer skips the listing page
entirely and goes straight to each of `source.models`' own overlay
fragment.

One overlay page lists EVERY document for that nameplate family - e.g.
Puma's has 5: the plain Puma price list (both a "vozy do výroby"/
production and a "skladové vozy"/stock-only version), the same split for
electric Puma Gen-E, and a Puma ST one. `_is_plain_model_pricelist` keeps
only the plain model's own price list (rejecting "Puma Gen-E ceník ..."/
"Puma ST ceník ..." by requiring the model name be immediately followed by
a "cen..." word - i.e. "Puma ceník", not "Puma Gen-E ceník" - or, for
Bronco's reversed phrasing, "Ceník Bronco" - and rejecting "Katalog ..."
brochures outright), and prefers a "vozy do výroby" (production) document
over a "skladové vozy" (stock-only) one when both exist - same "prefer the
current/regular document over a stock-only one" precedent as Mazda/Toyota.
Some models (verified for Mustang/Bronco 2026-09-07) only ever HAVE a
stock-only document at any given time - that's simply used as-is, not
treated as an error.

Ford's own price-list PDFs use a genuine trim x engine PRICE MATRIX
unlike every other brand parsed here - see parsers/ford.py's module
docstring for why only Puma/Kuga/Mustang/Bronco (of Ford's ~10-model
current CZ lineup) are covered so far."""

from __future__ import annotations

import re

import requests

from scraper.sources.registry import Source

from .base import BaseDiscoverer

_BASE_URL = "https://www.ford.cz"
_OVERLAY_URL = f"{_BASE_URL}/content/overlays/download-a-brochure-3-0/{{slug}}"
_MODEL_SLUGS = {
    "Puma": "puma-a-puma-gen-e",
    "Kuga": "kuga",
    "Mustang": "mustang",
    "Bronco": "bronco",
}
_PDF_LINK_RE = re.compile(r'<a[^>]*href="([^"]*\.pdf[^"]*)"[^>]*>(.*?)</a>', re.IGNORECASE | re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\s+")


def _link_text(raw_html: str) -> str:
    return _WHITESPACE_RE.sub(" ", _TAG_RE.sub(" ", raw_html)).strip()


def _is_plain_model_pricelist(text: str, model: str) -> bool:
    """Args:
        text: A PDF link's visible text (e.g. "Puma ceník (vozy do
            výroby) (PDF 2.2 MB)", "Ceník Bronco (PDF 1.5 MB)").
        model: The plain model name to match (e.g. "Puma") - NOT a
            sub-variant like "Puma Gen-E"/"Puma ST".

    Returns:
        `True` if `text` is this exact model's own price list (either
        word order, see module docstring) and not a brochure/catalog.
    """
    if "katalog" in text.lower():
        return False
    escaped = re.escape(model)
    model_then_cen = re.match(rf"^{escaped}\s+cen", text, re.IGNORECASE)
    cen_then_model = re.match(rf"^cen\S*\s+{escaped}\b", text, re.IGNORECASE)
    return bool(model_then_cen or cen_then_model)


class FordDiscoverer(BaseDiscoverer):
    def discover(self, source: Source, *, timeout: int = 30) -> dict[str, str]:
        """Args:
            source: Registry entry giving the models to discover - each
                fetches its own overlay fragment page, see module
                docstring for why (no shared listing-page fetch here).
            timeout: HTTP request timeout in seconds, applied per model.

        Returns:
            `{model: price_list_url}` for each of `source.models` with a
            known slug (`_MODEL_SLUGS`) whose overlay page had a matching
            price-list link - a model with no slug entry, an unreachable
            overlay page, or no matching link is simply omitted.
        """
        found: dict[str, str] = {}

        for model in source.models:
            slug = _MODEL_SLUGS.get(model)
            if slug is None:
                continue

            response = requests.get(_OVERLAY_URL.format(slug=slug), timeout=timeout)
            if response.status_code != 200:
                continue

            candidates = [(_link_text(raw_text), href) for href, raw_text in _PDF_LINK_RE.findall(response.text)]
            candidates = [(text, href) for text, href in candidates if _is_plain_model_pricelist(text, model)]
            if not candidates:
                continue

            production = [c for c in candidates if "výrob" in c[0].lower()]
            _text, href = production[0] if production else candidates[0]
            found[model] = _BASE_URL + href

        return found

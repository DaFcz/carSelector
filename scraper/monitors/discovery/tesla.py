"""Discoverer for tesla.com's own web configurator ("Design Studio").

Like Audi, Tesla doesn't publish a downloadable price-list PDF at all -
unlike Audi, it also has no separate JSON API endpoint to call directly.
Its own `/design` page for each model (e.g.
https://www.tesla.com/cs_cz/modely/design for Model Y) is server-rendered
with a `const dataJson = {...}` script embedding every trim, option and
CZK price for that model in one blob - see `parsers/tesla.py`'s own module
docstring for how that gets extracted.

There's no listing page to crawl for these URLs (Tesla's own model-
overview pages link straight to each model's own `/design` page) and only
two models are currently sold in the Czech Republic (verified 2026-09-14
on tesla.com/cs_cz - the homepage's own model carousel lists only Model Y
and Model 3; Model S/Model X have no CZ configurator page at all, matching
`doc/carVendors.md`'s own note on Tesla's shrunken current EU lineup), so
`discover` just returns both fixed URLs directly - same "no real discovery
needed" convention as Audi's/BMW's own single/fixed-URL discoverers.

Unlike every other brand here, a bare `requests.get()` - even with the
same full browser header set that clears Opel's/Peugeot's own Akamai WAF -
gets blocked on EVERY tesla.com path, not just a listing page (verified
2026-09-14: the homepage, the model pages and this discoverer's own
`/design` URLs all return a 403 "Access Denied" from AkamaiGHost). A
genuine browser (Playwright, headless or headed, with default fingerprint)
gets an Akamai Bot Manager JS sensor challenge instead of the real page,
and it did not resolve to real content in this environment either - a
strictly harder block than Opel's own (whose actual PDF endpoints, unlike
its listing page, ARE reachable via bare `requests`). See `sources.yaml`'s
own tesla entry for why it's registered here but not yet `active: true`."""
from __future__ import annotations

from scraper.sources.registry import Source

from .base import BaseDiscoverer

_DESIGN_STUDIO_URLS = {
    "Model Y": "https://www.tesla.com/cs_cz/modely/design",
    "Model 3": "https://www.tesla.com/cs_cz/model3/design",
}


class TeslaDiscoverer(BaseDiscoverer):
    def discover(self, source: Source) -> dict[str, str]:
        """Args:
            source: Registry entry for the tesla source - unused beyond
                the base interface (see module docstring for why there's
                no page to crawl and no per-model variation to resolve).

        Returns:
            `_DESIGN_STUDIO_URLS` - the same two fixed Design Studio URLs
            every time, one per model currently sold in the Czech Republic.
        """
        return dict(_DESIGN_STUDIO_URLS)

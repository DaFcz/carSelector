"""Discoverer for konfigurator.audi.cz.

Unlike every other brand here, Audi doesn't publish a downloadable price-
list PDF at all - audi.cz's own site has no "ceníky ke stažení" page or
link anywhere on it (verified 2026-09-14: neither the homepage nor the
"Všechny modely" model-overview page link one; the closest is a plain
"starting from" price shown per model line, with the real breakdown only
available through the web configurator). That configurator
(konfigurator.audi.cz) is a JS-rendered app, but its own network calls
reveal a plain JSON API behind it - `_MODELGROUP_URL` - that returns every
current model group's own variants, engines and prices in ONE response,
reachable with a bare `requests.get()` (no blocking, unlike Opel/
Peugeot's own WAFs). See parsers/audi.py's own module docstring for the
response shape and how it's turned into variants.

Like BMW's own single combined price list, one document covers Audi's
entire lineup - `discover` always returns the same `{"all": ...}` single
entry regardless of `source.models` (which is descriptive here, not a
filter - same convention as BMW's own sources.yaml comment)."""
from __future__ import annotations

from scraper.sources.registry import Source

from .base import BaseDiscoverer

_MODELGROUP_URL = "https://konfigurator.audi.cz/cc-cz/be/cs_CZ_AUDI23/api/v2/modelgroup?brand=A"


class AudiDiscoverer(BaseDiscoverer):
    def discover(self, source: Source) -> dict[str, str]:
        """Args:
            source: Registry entry for the audi source - unused beyond
                the base interface (see module docstring for why there's
                nothing to filter or vary here).

        Returns:
            `{"all": _MODELGROUP_URL}` - always the same single entry,
            since one API response covers every current model.
        """
        return {"all": _MODELGROUP_URL}

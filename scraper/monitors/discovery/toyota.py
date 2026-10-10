"""Discoverer for toyota.cz price lists.

The HTML listing page (toyota.cz/koupe-a-nabidky/ceniky) renders nothing
server-side — it's a client-side widget that itself calls a JSON API. The
real endpoint (found in the page's inline script, `PDF_API`/`B` variable)
is `https://pdf.sites.toyota.cz/api/models-documents`, which returns
groups of models, each with a `documents` list carrying the actual
`mainLink` download URL. (A second endpoint, `.../api/documents-model`,
looked similar at first but only returns filename metadata, no URLs —
not used here.)

Real-world messiness handled here, all verified against the live API on
2026-08-13:

- Every model has MANY documents (this year's + last year's price list,
  a "akce"/"limited_edition" promotional variant, catalogs, accessory
  price lists, ...) rather than one obvious "current" one.
  `_current_price_list` keeps only documents whose label/link doesn't
  contain "akce"/"limited_edition" (the promotional variants — same
  principle as VolkswagenDiscoverer excluding "Akční ceník modelu ..."),
  then picks the highest `id` (Toyota's API assigns ids in creation
  order, so the highest id among the remaining candidates is the current
  one — more robust than parsing a year out of the filename).
- A redesigned model can appear as TWO separate model entries: an old
  one under the plain name (e.g. "RAV4", "Yaris Cross") whose price list
  is stale, and a new one under a "Nová"/"Nový"/"Nové"-prefixed name
  (e.g. "Nová RAV4", "Nový Yaris Cross") that's actually current. Both
  collide on the same name once the marketing prefix is stripped —
  `_pick_current_generation` keeps the prefixed (current-generation) one
  on collision.
- Corolla is sold as three body styles (Sedan/Hatchback/Touring Sports),
  each a genuinely separate document — like Kia's Sportage ICE/HEV split,
  `source.models` has a single "Corolla" entry but this returns all three
  under distinct keys. "Corolla Cross" is deliberately NOT included here
  even though its name also starts with "Corolla" — Toyota positions it
  as its own (crossover) nameplate, not a Corolla body style.
"""

from __future__ import annotations

import requests

from scraper.sources.registry import Source

from .base import BaseDiscoverer

_API_URL = "https://pdf.sites.toyota.cz/api/models-documents?_format=json&filter[active]=true&sortBy[itemOrder]=asc"
_MARKETING_PREFIXES = ("Nová ", "Nový ", "Nové ", "Toyota ")
_EXCLUDE_DOC_MARKERS = ("akce", "limited_edition", "limited-edition")
_COROLLA_BODY_STYLES = {
    "Corolla Sedan": "Corolla Sedan",
    "Corolla Hatchback": "Corolla Hatchback",
    "Corolla TS Kombi": "Corolla Touring Sports",
}


def _strip_marketing_prefix(name: str) -> str:
    for prefix in _MARKETING_PREFIXES:
        if name.startswith(prefix):
            return name.removeprefix(prefix)
    return name


def _has_marketing_prefix(name: str) -> bool:
    return any(name.startswith(p) for p in _MARKETING_PREFIXES)


def _current_price_list(documents: list[dict]) -> str | None:
    candidates = [
        d
        for d in documents
        if d.get("active")
        and not any(m in d.get("label", "") or m in d.get("mainLink", "") for m in _EXCLUDE_DOC_MARKERS)
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda d: d["id"])["mainLink"]


class ToyotaDiscoverer(BaseDiscoverer):
    def discover(self, source: Source, *, timeout: int = 30) -> dict[str, str]:
        """Args:
            source: Registry entry giving the models to look for (the
                actual data source is Toyota's JSON API, `_API_URL`, not
                `source.source_url` - see module docstring).
            timeout: HTTP request timeout in seconds.

        Returns:
            `{model: price_list_url}` for each active model found in the
            API response, with Corolla's body styles handled specially
            (see module docstring) before the generic pass.
        """
        response = requests.get(_API_URL, timeout=timeout)
        response.raise_for_status()
        groups = response.json()
        all_models = [model for group in groups for model in group.get("models", []) if model.get("active")]

        found: dict[str, str] = {}

        # Corolla body styles (see module docstring) — handled before the
        # generic pass below since "Corolla" itself isn't a real model name.
        if "Corolla" in source.models:
            for model in all_models:
                key = _COROLLA_BODY_STYLES.get(model["originalModelName"])
                if key is None:
                    continue
                pdf_url = _current_price_list(model["documents"])
                if pdf_url:
                    found[key] = pdf_url

        best_by_base: dict[str, dict] = {}
        for model in all_models:
            original = model["originalModelName"]
            base = _strip_marketing_prefix(original)
            existing = best_by_base.get(base)
            if existing is None or (
                _has_marketing_prefix(original) and not _has_marketing_prefix(existing["originalModelName"])
            ):
                best_by_base[base] = model

        for model_name in source.models:
            if model_name == "Corolla" or model_name not in best_by_base:
                continue
            pdf_url = _current_price_list(best_by_base[model_name]["documents"])
            if pdf_url:
                found[model_name] = pdf_url

        return found

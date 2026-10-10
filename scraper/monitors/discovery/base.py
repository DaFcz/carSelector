"""Common interface for finding links to PDF price lists. Same principle as
`parsers/base.py`: both the structure and the number of pages that need to
be fetched differ from brand to brand, hence per-brand implementations
instead of one universal HTML parser — see the `pdf_pattern` field in
`config/sources.yaml`.

Making the HTTP request is deliberately part of `discover` (not done
upfront in `SourceMonitor` and passed in as `html`): Škoda has a single
listing page with all models (one GET), but VW has a separate price list
page per model (`source.models` GETs) — because the discoverer also
controls the fetch, each brand can have a different strategy without
`SourceMonitor` needing to change.

A new brand = a new file in this directory + registration in
`registry.py`, nothing else needs to change.
"""

from __future__ import annotations

from scraper.sources.registry import Source


class BaseDiscoverer:
    """Discoverer interface. `discover` must return {model: price_list_url}
    for the models in `source.models` for which a price list link was found."""

    def discover(self, source: Source) -> dict[str, str]:
        """Finds the current price-list PDF URL for each model this
        source covers. Deliberately makes its own HTTP request(s) rather
        than being handed pre-fetched HTML - see this module's docstring
        for why (each brand's page structure calls for a different fetch
        strategy).

        Args:
            source: Registry entry for one OEM/powertrain source (from
                `config/sources.yaml`), giving the page(s) to fetch and
                the `source.models` to look for.

        Returns:
            A `{model: price_list_url}` mapping, one entry per model in
            `source.models` for which a link was actually found - models
            with no discoverable link are simply omitted, not mapped to
            `None`.

        Raises:
            NotImplementedError: Always, on the base class - every
                concrete discoverer must override this.
        """
        raise NotImplementedError

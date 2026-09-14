"""Loads the source (OEM) registry from config/sources.yaml.

Anyone on the team can add a new brand by editing the YAML file, without
touching the downloader, monitor, or other brands' parsers.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "sources.yaml"


@dataclass(frozen=True)
class Source:
    brand: str
    country: str
    source_url: str | None
    pdf_pattern: str | None
    parser_key: str
    active: bool
    # Models belonging to this source. A single brand can have multiple
    # sources with the same source_url but a different parser_key (e.g.
    # Škoda: combustion models and EVs are on the same page, but have a
    # different PDF structure, and thus a different parser) — models then
    # determines which found documents belong to which source.
    models: list[str] = field(default_factory=list)
    # "pdf" (every brand so far), "json" (Audi's own price data comes from
    # its web configurator's JSON API, not a downloadable price-list PDF -
    # see parsers/audi.py's module docstring), or "html" (Tesla's own
    # price data is embedded inside its web configurator's server-rendered
    # HTML page instead - see parsers/tesla.py's module docstring).
    # SourceMonitor picks the matching downloader by this field;
    # ScraperPipeline skips the PDF-only release-date extraction step for
    # anything other than "pdf".
    content_type: str = "pdf"


class SourceRegistry:
    """Loads and provides sources (OEMs) from `config/sources.yaml`."""

    def __init__(self, config_path: Path = CONFIG_PATH) -> None:
        self._config_path = config_path

    def load_all(self) -> list[Source]:
        """Returns:
            Every source entry in `config/sources.yaml`, active or not.
        """
        data = yaml.safe_load(self._config_path.read_text(encoding="utf-8"))
        return [Source(**entry) for entry in data["sources"]]

    def load_active(self) -> list[Source]:
        """Returns:
            Only the sources with `active: true` - the ones
            `ScraperPipeline.run` actually processes.
        """
        return [s for s in self.load_all() if s.active]

    def get_by_parser_key(self, parser_key: str) -> Source | None:
        """Args:
            parser_key: `parser_key` value to look up (matches a key in
                `parsers/registry.py`'s `PARSERS`).

        Returns:
            The first source with this `parser_key`, or `None` if none match.
        """
        return next((s for s in self.load_all() if s.parser_key == parser_key), None)

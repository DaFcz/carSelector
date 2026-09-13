"""Downloads a JSON document and stores it under its hash, same principle
as `pdf_downloader.py` (auditability - an existing version is never
overwritten, and history can be traced). Needed because Audi's own price
data comes from its web configurator's JSON API rather than a downloadable
PDF price list - see parsers/audi.py's module docstring for why."""
from __future__ import annotations

from datetime import date
from pathlib import Path

import requests

from .pdf_downloader import STORAGE_ROOT, sha256_of


class JsonDownloader:
    """Downloads JSON documents and stores them at
    storage/scraper/<brand>/<year>/<hash>.json - same layout and
    dedup-by-hash behavior as `PdfDownloader`, just a different extension
    so the stored file's own name doesn't misrepresent its content type.

    `storage_root` is injectable (e.g. for tests with a temp directory)."""

    def __init__(self, storage_root: Path = STORAGE_ROOT) -> None:
        self._storage_root = storage_root

    def download(self, url: str, brand: str, *, timeout: int = 30) -> tuple[Path, str]:
        """Args:
            url: URL of the JSON document to download.
            brand: Brand key this document belongs to (used as the
                storage subdirectory).
            timeout: HTTP request timeout in seconds.

        Returns:
            `(file_path, sha256_hash)` - same contract as
            `PdfDownloader.download`.
        """
        response = requests.get(url, timeout=timeout)
        response.raise_for_status()
        content = response.content

        file_hash = sha256_of(content)
        year_dir = self._storage_root / brand / str(date.today().year)
        year_dir.mkdir(parents=True, exist_ok=True)

        target = year_dir / f"{file_hash}.json"
        if not target.exists():
            target.write_bytes(content)

        return target, file_hash

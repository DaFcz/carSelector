"""Downloads an HTML document and stores it under its hash, same principle
as `pdf_downloader.py`/`json_downloader.py` (auditability - an existing
version is never overwritten, and history can be traced). Needed because
Tesla's own price data isn't a downloadable PDF or a plain JSON API
response like Audi's - it's embedded as a `const dataJson = {...}` script
inside the server-rendered HTML of its own web configurator ("Design
Studio") page - see `parsers/tesla.py`'s module docstring for how that
gets extracted, and `monitors/discovery/tesla.py`'s for why a bare
`requests.get()` (even with a full browser header set) can't fetch that
page at all."""
from __future__ import annotations

from datetime import date
from pathlib import Path

import requests

from .pdf_downloader import STORAGE_ROOT, _BROWSER_HEADERS, sha256_of


class HtmlDownloader:
    """Downloads HTML documents and stores them at
    storage/scraper/<brand>/<year>/<hash>.html - same layout and
    dedup-by-hash behavior as `PdfDownloader`/`JsonDownloader`, just a
    different extension so the stored file's own name doesn't misrepresent
    its content type.

    `storage_root` is injectable (e.g. for tests with a temp directory)."""

    def __init__(self, storage_root: Path = STORAGE_ROOT) -> None:
        self._storage_root = storage_root

    def download(self, url: str, brand: str, *, timeout: int = 30) -> tuple[Path, str]:
        """Args:
            url: URL of the HTML document to download.
            brand: Brand key this document belongs to (used as the
                storage subdirectory).
            timeout: HTTP request timeout in seconds.

        Returns:
            `(file_path, sha256_hash)` - same contract as
            `PdfDownloader.download`.
        """
        response = requests.get(url, headers=_BROWSER_HEADERS, timeout=timeout)
        response.raise_for_status()
        content = response.content

        file_hash = sha256_of(content)
        year_dir = self._storage_root / brand / str(date.today().year)
        year_dir.mkdir(parents=True, exist_ok=True)

        target = year_dir / f"{file_hash}.html"
        if not target.exists():
            target.write_bytes(content)

        return target, file_hash

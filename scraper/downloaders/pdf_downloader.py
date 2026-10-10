"""Downloads a PDF and stores it under its hash, so an existing version is
never overwritten and history can be traced (auditability, see the
architecture doc)."""

from __future__ import annotations

import hashlib
from datetime import date
from pathlib import Path

import requests

# Repo-root storage/scraper/, not scraper/storage/ - all local data files
# (this module's downloads, scraper.db, backend's drivewise.db, the hand-
# picked fixture PDFs in storage/cars/) live under one top-level storage/
# directory - see storage/README.md.
STORAGE_ROOT = Path(__file__).resolve().parents[2] / "storage" / "scraper"

# A bare `requests` GET (no headers at all) gets a 403 from an Akamai WAF
# in front of Opel's own CDN specifically (verified 2026-09-12) - every
# other brand's CDN accepts a bare request fine, so this was never needed
# before. A realistic full browser fingerprint clears it; a partial one
# (tested individually: User-Agent alone, +Accept, +Accept-Language,
# +Referer, +Sec-Fetch-* alone, +sec-ch-ua* alone) does not - Akamai's
# check appears to score how many "this looks like a real browser
# navigation" signals are present together, not any single header, so a
# comprehensive set is the robust choice here rather than a minimal one
# that might stop clearing it if that scoring shifts slightly. No
# `Referer` needed - `Sec-Fetch-Site: none` (what a real browser sends for
# a direct, un-referred navigation) is enough, which also keeps this
# usable for any brand's URL without knowing which page "referred" it.
# Confirmed harmless for every other already-working brand's own CDN
# (Dacia/Ford/CUPRA all still 200 with this applied).
_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "cs-CZ,cs;q=0.9,en;q=0.8",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "sec-ch-ua": '"Chromium";v="131", "Not_A Brand";v="24"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
}


def sha256_of(content: bytes) -> str:
    """Args:
        content: Raw bytes to hash.

    Returns:
        Hex-encoded SHA-256 digest of `content`.
    """
    return hashlib.sha256(content).hexdigest()


class PdfDownloader:
    """Downloads PDFs and stores them under their hash, so an existing
    version is never overwritten and history can be traced (auditability,
    see the architecture doc).

    `storage_root` is injectable (e.g. for tests with a temp directory)."""

    def __init__(self, storage_root: Path = STORAGE_ROOT) -> None:
        self._storage_root = storage_root

    def download(self, url: str, brand: str, *, timeout: int = 30) -> tuple[Path, str]:
        """Downloads the PDF and stores it at storage/scraper/<brand>/<year>/<hash>.pdf.

        Args:
            url: URL of the PDF to download.
            brand: Brand key this PDF belongs to (used as the storage
                subdirectory).
            timeout: HTTP request timeout in seconds.

        Returns:
            `(file_path, sha256_hash)` - `file_path` is where the PDF now
            lives on disk (already existed there if this exact content
            was downloaded before); `sha256_hash` is compared in the
            monitor against the document table so the same content is
            never processed twice.
        """
        response = requests.get(url, headers=_BROWSER_HEADERS, timeout=timeout)
        response.raise_for_status()
        content = response.content

        file_hash = sha256_of(content)
        year_dir = self._storage_root / brand / str(date.today().year)
        year_dir.mkdir(parents=True, exist_ok=True)

        target = year_dir / f"{file_hash}.pdf"
        if not target.exists():
            target.write_bytes(content)

        return target, file_hash

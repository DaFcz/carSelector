"""Checks whether there's a new price-list document (by SHA256 hash), and
if so, downloads it and writes a record to the `document` table.

Finding the specific document links (how many pages to fetch, where the
links are) is per-brand logic — see `discovery/` (Škoda: a single listing
page with all models; VW: a separate page per model). The fetch is part of
the discoverer; `SourceMonitor` just passes it the `source`.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from scraper.database.models import Document
from scraper.downloaders.json_downloader import JsonDownloader
from scraper.downloaders.pdf_downloader import PdfDownloader
from scraper.monitors.discovery.registry import DISCOVERERS
from scraper.sources.registry import Source


class SourceMonitor:
    """Finds new documents for a given source and stores them in the DB."""

    def __init__(
        self,
        session: Session,
        downloader: PdfDownloader | None = None,
        json_downloader: JsonDownloader | None = None,
    ) -> None:
        self._session = session
        self._downloader = downloader or PdfDownloader()
        self._json_downloader = json_downloader or JsonDownloader()

    def check_and_store(self, source: Source, pdf_url: str) -> Document | None:
        """Downloads the document, and if its hash isn't in the DB yet, creates a new Document.

        Args:
            source: The source this document belongs to (for
                `source.brand`/`source.content_type`).
            pdf_url: URL of the document to download and check (a PDF for
                every brand except Audi, whose own `content_type` is
                "json" - see `sources/registry.py`'s own docstring).

        Returns:
            The newly created `Document`, or `None` if a document with
            this exact content (same brand + SHA256 hash) already exists.
        """
        downloader = self._json_downloader if source.content_type == "json" else self._downloader
        path, file_hash = downloader.download(pdf_url, brand=source.brand)

        existing = (
            self._session.query(Document)
            .filter_by(source_brand=source.brand, sha256_hash=file_hash)
            .first()
        )
        if existing:
            return None  # already processed, nothing new

        document = Document(
            source_brand=source.brand,
            document_url=pdf_url,
            sha256_hash=file_hash,
            file_path=str(path),
        )
        self._session.add(document)
        self._session.commit()
        return document

    def fetch_new_documents(self, source: Source) -> list[Document]:
        """Uses the matching Discoverer to find price list links for the
        models in `source.models` and creates a Document for each new one
        (by SHA256). Returns only newly created records (already-processed
        PDFs are skipped, see check_and_store).

        Args:
            source: Source to find and store new documents for.

        Returns:
            Newly created `Document` rows (empty if none are new, or if
            `source.parser_key` has no registered discoverer).
        """
        discoverer_cls = DISCOVERERS.get(source.parser_key)
        if discoverer_cls is None:
            return []

        price_list_urls = discoverer_cls().discover(source)

        new_documents = []
        for pdf_url in price_list_urls.values():
            document = self.check_and_store(source, pdf_url)
            if document is not None:
                new_documents.append(document)
        return new_documents

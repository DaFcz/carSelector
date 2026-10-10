"""CLI for manually verifying extracted data against the source PDF.

Goal: never trust the parser blindly. For a given document, prints every
extracted variant/price along with the page and raw text the record was
built from, so it can be quickly checked against the open PDF.

Usage:
    python -m scraper.verification.review_cli --document-id 1
"""

from __future__ import annotations

import click
from sqlalchemy.orm import Session

from scraper.database.db import get_session
from scraper.database.models import Document, PriceHistory, Variant
from scraper.database.repositories import DocumentRepository, VariantRepository


class ReviewService:
    """DB queries for manually verifying extracted data — separated from
    the CLI (click) layer so it can be tested/used outside the command line too."""

    def __init__(self, session: Session) -> None:
        self._documents = DocumentRepository(session)
        self._variants = VariantRepository(session)

    def get_document(self, document_id: int) -> Document | None:
        return self._documents.get(document_id)

    def get_variants_with_prices(self, document_id: int) -> list[tuple[Variant, list[PriceHistory]]]:
        variants = self._variants.list_for_document(document_id)
        return [(variant, self._variants.list_prices(variant.id)) for variant in variants]


@click.command()
@click.option("--document-id", type=int, required=True)
def review(document_id: int) -> None:
    service = ReviewService(get_session())
    document = service.get_document(document_id)
    if document is None:
        click.echo(f"Document {document_id} not found.")
        return

    click.echo(f"Document: {document.source_brand} — {document.document_url}")
    click.echo(f"SHA256: {document.sha256_hash}")
    click.echo("-" * 60)

    for variant, prices in service.get_variants_with_prices(document_id):
        click.echo(f"[page {variant.source_page}] {variant.variant_name}")
        click.echo(f"  raw: {variant.raw_text!r}")
        for price in prices:
            click.echo(f"  price: {price.price} {price.currency} (valid from {price.valid_from})")
        click.echo()


if __name__ == "__main__":
    review()

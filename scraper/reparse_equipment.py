"""Re-parses already-downloaded price lists and refreshes the stored
equipment of their variants - for when a parser learns to read more
equipment than it did when the document was first scraped.

`python -m scraper.main` can't do this: it only processes NEW documents
(hash-based dedup, see monitors/source_monitor.py), so an unchanged price
list is never parsed again. This works from the local copies only
(`document.file_path`) - nothing is downloaded.

Only equipment changes. Variants, prices and price history stay as they
are; a stored variant is matched to fresh parser output by
(variant_name, trim, source_page), and one without a match is reported
and left untouched rather than guessed at.

Usage (repo root):

    python -m scraper.reparse_equipment --brand skoda
    python -m scraper.reparse_equipment --brand skoda --dry-run

Then re-run `scripts/import_scraper_data.py` to bring the result into the
app's database.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import click
from sqlalchemy.orm import Session

from scraper.database.db import get_session, init_db
from scraper.database.models import Document, Variant
from scraper.database.repositories import VariantRepository
from scraper.parsers.base import BaseParser, ExtractedVariant
from scraper.parsers.registry import PARSERS

_VariantKey = tuple[str, str | None, int]


def _parser_for(brand: str, powertrain: str) -> type[BaseParser] | None:
    """The registered parser for `brand` + `powertrain` (Škoda has one per
    powertrain, see parsers/base.py), or None if there isn't exactly one."""
    matches = [cls for cls in PARSERS.values() if cls.brand == brand and cls.powertrain == powertrain]
    return matches[0] if len(matches) == 1 else None


def _key(variant: Variant | ExtractedVariant) -> _VariantKey:
    return variant.variant_name, variant.trim, variant.source_page


def reparse_document(session: Session, document: Document, dry_run: bool = False) -> Counter:
    """Refreshes the equipment of every stored variant of `document`.

    Args:
        session: Scraper DB session.
        document: A stored document whose file still exists locally.
        dry_run: Parse and count, but don't write anything.

    Returns:
        Counts: `updated` variants, `unmatched` stored variants, and
        `skipped` ones (no single parser for their brand/powertrain).
    """
    counts: Counter = Counter()
    repository = VariantRepository(session)
    by_powertrain: dict[str, list[Variant]] = {}
    for variant in document.variants:
        by_powertrain.setdefault(variant.powertrain, []).append(variant)

    for powertrain, stored in by_powertrain.items():
        parser_cls = _parser_for(document.source_brand, powertrain)
        if parser_cls is None:
            counts["skipped"] += len(stored)
            continue
        fresh = {_key(extracted): extracted for extracted in parser_cls().parse(Path(document.file_path))}
        for variant in stored:
            extracted = fresh.get(_key(variant))
            if extracted is None:
                counts["unmatched"] += 1
                continue
            if not dry_run:
                repository.replace_equipment(variant, extracted)
            counts["updated"] += 1

    if not dry_run:
        session.commit()
    return counts


@click.command()
@click.option("--brand", required=True, help="Brand key as stored in document.source_brand, e.g. skoda.")
@click.option("--dry-run", is_flag=True, help="Parse and report, but don't write anything.")
def main(brand: str, dry_run: bool) -> None:
    """Re-parses every stored document of BRAND and refreshes its variants' equipment."""
    init_db()
    session = get_session()
    try:
        documents = session.query(Document).filter(Document.source_brand == brand).order_by(Document.id).all()
        for document in documents:
            if not Path(document.file_path).is_file():
                click.echo(f"document {document.id}: file missing, skipped ({document.file_path})")
                continue
            counts = reparse_document(session, document, dry_run=dry_run)
            click.echo(f"document {document.id}: {dict(counts)}")
    finally:
        session.close()


if __name__ == "__main__":
    main()

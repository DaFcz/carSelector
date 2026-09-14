#!/usr/bin/env python3
"""Imports scraper's parsed price-list data (storage/scraper.db) into the
backend's normalized catalog (storage/drivewise.db, or wherever
DATABASE_URL points).

scraper/ and backend/ deliberately use two different schemas (document-
centric vs. normalized catalog) with no live pipeline between them - see
storage/README.md and the drivewise-data-model skill. This script is that
missing one-way import step. It's a standalone script, not part of either
service's request path - run it manually after a scrape:

    python scripts/import_scraper_data.py [--dry-run]

Safe to re-run: brands/models/trims/powertrains/configurations are looked
up by natural key before creating, and prices only get a new row when the
price actually changed (closing the previous one) - matching the
append-only design in app/models/price.py.

Equipment/options: scraper's equipment_assignment now carries a
surcharge_amount for the one format that has one so far (Škoda's
"Samostatné prvky výbavy" page, see parsers/skoda_equipment.py) - those
rows import as option_items/option_availability (category=equipment).
Rows this still can't import, without fabricating data:
- OPTIONAL rows with no surcharge_amount (no price to satisfy drivewise's
  'optional' CHECK constraint) - counted in equipment_skipped.
- PACKAGE rows - drivewise's AvailabilityStatus has no equivalent state
  yet (standard/optional/unavailable only) - counted in equipment_skipped.
scraper's STANDARD/NOT_AVAILABLE map onto drivewise's standard/unavailable
directly (no surcharge needed for either).

What it still deliberately does NOT import (documented gaps, not silently
dropped):
- model.category (body type), model_year, colors, and most of
  powertrains' spec columns (transmission, displacement_cc, consumption,
  co2, ...): none of these are structured fields in scraper's schema, only
  free text in variant_name/raw_text. Left null, same "not derivable from
  the source" stance already documented for the hand-seeded fixtures.
- fuel_type/drivetrain ARE inferred from variant_name text (see
  infer_fuel_type/infer_drivetrain below) since drivewise requires them
  (NOT NULL) - this is a heuristic, not a parse of a structured field, and
  can be wrong on unusual naming. power_kw is opportunistically extracted
  the same way, staying None where no reliable "NNN kW" substring exists
  (e.g. Toyota's price lists only state hp, not kW).

Note: `powertrains.manufacturer_code` is repurposed here to hold a
fingerprint of this script's own dedup key (see signature_fingerprint),
not a real manufacturer order code - only rows created by this script use
it that way.

Code style: the free functions below (slugify, infer_fuel_type, ...) are
small, stateless, single-purpose helpers with no shared state - per
drivewise-architecture's Code style section, they stay plain functions.
`ScraperDataImporter` is the opposite case (a run's per-brand/model/trim/
powertrain/configuration/source-document caches genuinely are shared,
mutated state across every get_or_create_* call for that run) - a class,
with the caches as instance attributes instead of a dict threaded through
every function call.
"""
from __future__ import annotations

import argparse
import hashlib
import re
import sqlite3
import sys
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.db.session import SessionLocal  # noqa: E402
from app.models import (  # noqa: E402
    Brand,
    CarModel,
    Configuration,
    OptionAvailability,
    OptionItem,
    Powertrain,
    Price,
    SourceDocument,
    Trim,
)
from app.models.enums import (  # noqa: E402
    AvailabilityStatus,
    DocumentType,
    Drivetrain,
    FuelType,
    OptionCategory,
)

SCRAPER_DB_PATH = REPO_ROOT / "storage" / "scraper.db"
MARKET = "CZ"
LOCALE = "cs-CZ"

# scraper/'s source_brand keys are already valid slugs (lowercase, no
# accents); only the display name needs real casing/diacritics.
BRAND_NAMES = {
    "skoda": "Škoda",
    "volkswagen": "Volkswagen",
    "kia": "Kia",
    "toyota": "Toyota",
    "hyundai": "Hyundai",
    "mercedes-benz": "Mercedes-Benz",
    "mazda": "Mazda",
    "bmw": "BMW",
    "dacia": "Dacia",
    "ford": "Ford",
    "cupra": "CUPRA",
    "renault": "Renault",
    "opel": "Opel",
    "peugeot": "Peugeot",
    "mg": "MG",
    "audi": "Audi",
    "tesla": "Tesla",
}

_SCRAPER_TO_FUEL_TYPE = {
    "EV": FuelType.electric,
    "MHEV": FuelType.mild_hybrid,
    "PHEV": FuelType.phev,
    "HEV": FuelType.hybrid,
    # "ICE" is ambiguous (petrol vs. diesel) - resolved in infer_fuel_type.
}

_KW_RE = re.compile(r"(\d+)\s*kW", re.IGNORECASE)
# "4×4" (Dacia's own marker, e.g. "hybrid 150 4×4") uses the real
# multiplication sign U+00D7, not a literal "x" - "4x4" alone wouldn't match it.
# "4WD" (CUPRA's own marker, e.g. "2.0 TSI 204k DSG 4WD") is yet another
# spelling none of the others cover. "všech kol" ("all wheels") is Tesla's
# own wording (e.g. "... s pohonem všech kol Dual Motor") - its own price
# data never uses a marker any of the other alternatives here would catch.
_AWD_RE = re.compile(r"4x4|4×4|4wd|4motion|awd|quattro|4matic|xdrive|všech kol", re.IGNORECASE)
# MG's own POHON (drivetrain) column is printed per row, in Czech, and
# kept verbatim in variant_name - "zadní" ("rear") is the one other
# brands here don't expose plainly enough to be worth a general marker
# for (see infer_drivetrain's own docstring on that gap). `\w*` (not a
# bare `\b`) also matches Tesla's own inflected "zadních" ("... s pohonem
# zadních kol"), which the plain word "zadní" alone never appears as.
_RWD_RE = re.compile(r"\bzadní\w*\b", re.IGNORECASE)
# \d{2,3}d\b: BMW's own diesel suffix ("118d", "320d", "M340d" - fused
# directly onto the trim's number with no space, unlike Mercedes-Benz's
# "220 d" - see bmw.py's module docstring). Doesn't need a leading \b
# since "M340d" has no word-boundary between "M" and "3".
# CDTI: Opel/Stellantis's own diesel badge (e.g. "1.5 CDTI (96kW/130k)") -
# needs its own alternative rather than folding into \bTDI\b, since "CDTI"
# has no word boundary before the "TDI" substring it contains. HDi: fellow
# Stellantis brand Peugeot's own diesel badge, almost always fused onto a
# "Blue" prefix with no separator ("BlueHDi 130 EAT8") - same reasoning,
# no leading \b since "Blue"+"HDi" has no word boundary between them either.
_DIESEL_RE = re.compile(r"\bTDI\b|\bCRDI\b|\bCDTI\b|HDi\b|diesel|\d{2,3}d\b", re.IGNORECASE)

# scraper's equipment_assignment.availability values that map onto
# drivewise's AvailabilityStatus - PACKAGE is deliberately absent (no
# equivalent state exists yet, see this module's docstring).
_SCRAPER_TO_AVAILABILITY_STATUS = {
    "STANDARD": AvailabilityStatus.standard,
    "OPTIONAL": AvailabilityStatus.optional,
    "NOT_AVAILABLE": AvailabilityStatus.unavailable,
}


def humanize_equipment_name(canonical_name: str) -> str:
    """Args:
        canonical_name: scraper's `equipment.canonical_name` - a
            normalized slug (`EquipmentNormalizer`), e.g.
            `"příprava_pro_tažné_zařízení"` or `"heated_seats"`.

    Returns:
        `canonical_name` with underscores turned back into spaces and its
        first character capitalized - readable enough for
        `option_items.name` given scraper's schema has no separate
        display-name field yet (only the normalized slug).
    """
    text = canonical_name.replace("_", " ").strip()
    return text[:1].upper() + text[1:] if text else text


def slugify(text: str) -> str:
    """Args:
        text: Free-text name to turn into a URL/slug-safe identifier.

    Returns:
        `text` lowercased, with diacritics stripped and any run of
        non-alphanumeric characters collapsed to a single hyphen (leading/
        trailing hyphens removed). `"x"` if that leaves nothing (e.g.
        `text` was purely punctuation).
    """
    normalized = unicodedata.normalize("NFKD", text)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", ascii_text).strip("-").lower()
    return slug or "x"


def infer_fuel_type(scraper_powertrain: str, variant_name: str) -> FuelType:
    """Args:
        scraper_powertrain: scraper's own `variant.powertrain` value -
            one of `"ICE"`, `"EV"`, `"MHEV"`, `"PHEV"`, `"HEV"`.
        variant_name: The variant's display name, used only to split
            `"ICE"` into petrol/diesel (the other values map directly).

    Returns:
        The drivewise `FuelType` this variant most likely is. Every value
        except `"ICE"` maps 1:1 via `_SCRAPER_TO_FUEL_TYPE`; `"ICE"`
        resolves to `diesel` if `variant_name` contains a diesel marker
        (TDI/CRDI/"diesel", or BMW's own fused "NNNd" suffix), else
        `petrol`.
    """
    if scraper_powertrain in _SCRAPER_TO_FUEL_TYPE:
        return _SCRAPER_TO_FUEL_TYPE[scraper_powertrain]
    # scraper_powertrain == "ICE": split into petrol/diesel from the name.
    return FuelType.diesel if _DIESEL_RE.search(variant_name) else FuelType.petrol


def infer_drivetrain(variant_name: str) -> Drivetrain:
    """Args:
        variant_name: The variant's display name to scan for an
            AWD/4x4-style marker (4x4, 4Motion, AWD, quattro, 4MATIC, xDrive).

    Returns:
        `Drivetrain.awd` if a marker was found, else `Drivetrain.rwd` if
        MG's own "zadní" ("rear") marker was found, else `Drivetrain.fwd`.
        RWD isn't distinguishable from the naming most brands here use for
        these segments, so defaulting the rest to fwd was accurate for
        them - BMW is the exception (plenty of genuinely rear-wheel-drive
        trims, e.g. plain "320i"/"M4" with no xDrive/sDrive marker at
        all), but telling those apart from BMW's front-wheel-drive-
        platform models (1 Series, X1/X2 without xDrive) would need
        knowing which model FAMILY a row belongs to, not just scanning
        its own text - out of scope for this brand-agnostic heuristic, so
        BMW's non-xDrive trims fall into the same accepted fwd-default gap
        as everyone else's for now. MG doesn't share that gap: its own
        price tables print POHON (drivetrain) explicitly per row, so
        "zadní" is read directly rather than guessed.
    """
    if _AWD_RE.search(variant_name):
        return Drivetrain.awd
    if _RWD_RE.search(variant_name):
        return Drivetrain.rwd
    return Drivetrain.fwd


def extract_power_kw(text: str) -> int | None:
    """Args:
        text: Free text to search for a "NNN kW" substring.

    Returns:
        The first power figure found in kW, or `None` if `text` has no
        such substring (e.g. Toyota's price lists only state hp).
    """
    m = _KW_RE.search(text)
    return int(m.group(1)) if m else None


def powertrain_signature(variant_name: str, trim: str) -> str:
    """A stable per-model dedup key for 'the same engine' across trims -
    the variant name with the (already separately tracked) trim name
    removed, since scraper's variant_name = model + trim + engine spec in
    an order that differs by brand (trim is sometimes in the middle,
    sometimes at the end) - see this script's module docstring.

    Args:
        variant_name: scraper's `variant.variant_name` for this row.
        trim: The already-extracted trim name to strip out of
            `variant_name`, wherever it occurs.

    Returns:
        `variant_name` with the first occurrence of `trim` removed,
        whitespace-collapsed and lowercased. Two variants within the same
        model that resolve to the same signature are treated as the same
        underlying engine (see `ScraperDataImporter.get_or_create_powertrain`).
    """
    remainder = variant_name.replace(trim, "") if trim else variant_name
    return re.sub(r"\s+", " ", remainder).strip().lower()


def signature_fingerprint(signature: str) -> str:
    """Short, deterministic stand-in for `signature` that fits in
    Powertrain.manufacturer_code (String(32)) - used as the persisted
    identity for matching 'the same engine' across separate runs of this
    script (see ScraperDataImporter.get_or_create_powertrain).
    (fuel_type, drivetrain, power_kw) alone isn't a reliable identity:
    two genuinely different engines within a model can share all three
    (e.g. two similarly-tuned petrol FWD variants), so a rerun without
    this would risk silently merging or splitting powertrains rather
    than matching the exact one this script created originally.

    Args:
        signature: Output of `powertrain_signature` to fingerprint.

    Returns:
        A short, deterministic, collision-resistant-enough string
        (`"scr:"` + 24 hex chars of a SHA-256 digest) safe to store in a
        `String(32)` column.
    """
    return "scr:" + hashlib.sha256(signature.encode("utf-8")).hexdigest()[:24]


@dataclass
class ImportStats:
    """Counts accumulated over one `ScraperDataImporter.run()` call, for
    the end-of-run summary printout."""

    brands: int = 0
    models: int = 0
    trims: int = 0
    powertrains: int = 0
    configurations: int = 0
    source_documents: int = 0
    prices_inserted: int = 0
    prices_unchanged: int = 0
    option_items: int = 0
    option_availabilities_inserted: int = 0
    option_availabilities_updated: int = 0
    option_availabilities_unchanged: int = 0
    equipment_skipped: int = 0
    warnings: list[str] = field(default_factory=list)


class ScraperDataImporter:
    """Imports one scraper.db's worth of documents/variants/prices into a
    backend DB session, per this module's docstring. One instance = one
    import run: the natural-key caches below are genuinely per-run
    mutable state shared across every `get_or_create_*` call, which is
    exactly the "real behavior grouped around state" case for a class
    per `drivewise-architecture`'s Code style section.
    """

    def __init__(self, db: Session, scraper_con: sqlite3.Connection) -> None:
        """Args:
            db: Backend database session to write the imported catalog
                into. Not committed by this class - the caller commits
                (or rolls back, for `--dry-run`) after `run()` returns.
            scraper_con: Read-only connection to scraper.db to import from.
        """
        self._db = db
        self._scraper_con = scraper_con
        self.stats = ImportStats()
        self._brand_cache: dict[str, Brand] = {}
        self._model_cache: dict[tuple[int, str], CarModel] = {}
        self._trim_cache: dict[tuple[int, str], Trim] = {}
        self._powertrain_cache: dict[tuple[int, str], Powertrain] = {}
        self._configuration_cache: dict[tuple[int, int], Configuration] = {}
        self._source_document_cache: dict[tuple[str, int], SourceDocument] = {}
        self._option_item_cache: dict[tuple[int, str], OptionItem] = {}

    def get_or_create_brand(self, slug: str) -> Brand:
        """Args:
            slug: scraper's `source_brand` value (already a valid slug).

        Returns:
            The existing `Brand` row for `slug`, or a newly created one
            (display name from `BRAND_NAMES`, falling back to
            `slug.title()` for an unmapped brand).
        """
        if slug in self._brand_cache:
            return self._brand_cache[slug]
        brand = self._db.scalar(select(Brand).where(Brand.slug == slug))
        if brand is None:
            brand = Brand(slug=slug, name=BRAND_NAMES.get(slug, slug.title()))
            self._db.add(brand)
            self._db.flush()
        self._brand_cache[slug] = brand
        return brand

    def get_or_create_model(self, brand: Brand, name: str) -> CarModel:
        """Args:
            brand: The model's brand (`models.brand_id` FK).
            name: Display name, e.g. `"Octavia"` - also slugified for the
                `(brand_id, slug)` natural key.

        Returns:
            The existing `CarModel` row for `(brand, slugify(name))`, or a
            newly created one.
        """
        slug = slugify(name)
        key = (brand.id, slug)
        if key in self._model_cache:
            return self._model_cache[key]
        model = self._db.scalar(
            select(CarModel).where(CarModel.brand_id == brand.id, CarModel.slug == slug)
        )
        if model is None:
            model = CarModel(brand_id=brand.id, slug=slug, name=name)
            self._db.add(model)
            self._db.flush()
        self._model_cache[key] = model
        return model

    def get_or_create_trim(self, model: CarModel, name: str) -> Trim:
        """Args:
            model: The trim's model (`trims.model_id` FK).
            name: Trim display name, e.g. `"Selection"`.

        Returns:
            The existing `Trim` row for `(model, name)`, or a newly
            created one.
        """
        key = (model.id, name)
        if key in self._trim_cache:
            return self._trim_cache[key]
        trim = self._db.scalar(select(Trim).where(Trim.model_id == model.id, Trim.name == name))
        if trim is None:
            trim = Trim(model_id=model.id, name=name)
            self._db.add(trim)
            self._db.flush()
        self._trim_cache[key] = trim
        return trim

    def get_or_create_powertrain(
        self,
        model: CarModel,
        signature: str,
        fuel_type: FuelType,
        drivetrain: Drivetrain,
        power_kw: int | None,
    ) -> Powertrain:
        """Args:
            model: The powertrain's model (`powertrains.model_id` FK).
            signature: Output of `powertrain_signature` for this variant -
                fingerprinted (see `signature_fingerprint`) and stored in
                `manufacturer_code` as this row's persisted identity.
            fuel_type: Inferred fuel type (see `infer_fuel_type`) - only
                used when actually creating a new row.
            drivetrain: Inferred drivetrain (see `infer_drivetrain`) -
                only used when actually creating a new row.
            power_kw: Extracted power in kW, or `None` (see
                `extract_power_kw`) - only used when actually creating a
                new row.

        Returns:
            The existing `Powertrain` row for `(model,
            signature_fingerprint(signature))`, or a newly created one.
            No DB-level natural-key constraint on powertrains (unlike the
            other tables) - the fingerprint in `manufacturer_code` is
            this script's own persisted identity, so a fresh process
            (empty in-memory cache) still matches the exact powertrain a
            previous run created, not just one that happens to share
            fuel_type/drivetrain/power_kw.
        """
        key = (model.id, signature)
        if key in self._powertrain_cache:
            return self._powertrain_cache[key]
        fingerprint = signature_fingerprint(signature)
        powertrain = self._db.scalar(
            select(Powertrain).where(
                Powertrain.model_id == model.id,
                Powertrain.manufacturer_code == fingerprint,
            )
        )
        if powertrain is None:
            powertrain = Powertrain(
                model_id=model.id,
                manufacturer_code=fingerprint,
                fuel_type=fuel_type,
                drivetrain=drivetrain,
                power_kw=power_kw,
            )
            self._db.add(powertrain)
            self._db.flush()
        self._powertrain_cache[key] = powertrain
        return powertrain

    def get_or_create_configuration(self, trim: Trim, powertrain: Powertrain) -> Configuration:
        """Args:
            trim: The configuration's trim.
            powertrain: The configuration's powertrain.

        Returns:
            The existing `Configuration` row for `(trim, powertrain)`
            (drivewise's own `UNIQUE(trim_id, powertrain_id)` constraint
            backs this lookup), or a newly created one.
        """
        key = (trim.id, powertrain.id)
        if key in self._configuration_cache:
            return self._configuration_cache[key]
        configuration = self._db.scalar(
            select(Configuration).where(
                Configuration.trim_id == trim.id, Configuration.powertrain_id == powertrain.id
            )
        )
        if configuration is None:
            configuration = Configuration(trim_id=trim.id, powertrain_id=powertrain.id)
            self._db.add(configuration)
            self._db.flush()
        self._configuration_cache[key] = configuration
        return configuration

    def get_or_create_source_document(
        self,
        model: CarModel,
        file_path: str,
        release_date: str | None,
        downloaded_at: str,
    ) -> SourceDocument:
        """Args:
            model: The document's model - one `document.file_path` can
                cover several models (Mercedes-Benz's combined price list
                does, see `run`'s docstring), so the natural key here is
                `(file_path, model)`, not `file_path` alone - one
                `SourceDocument` row per model sharing that file.
            file_path: scraper's `document.file_path`.
            release_date: scraper's `document.release_date`
                (`YYYY-MM-DD`), or `None` (Kia/Toyota/Mercedes-Benz don't
                always have one - see `drivewise-scraper`).
            downloaded_at: scraper's `document.downloaded_at` timestamp,
                used as `effective_date`'s fallback when `release_date`
                is `None`, and always as `retrieved_at`.

        Returns:
            The existing `SourceDocument` row for `(file_path, model)`, or
            a newly created one.
        """
        key = (file_path, model.id)
        if key in self._source_document_cache:
            return self._source_document_cache[key]
        source_document = self._db.scalar(
            select(SourceDocument).where(
                SourceDocument.file_path == file_path, SourceDocument.model_id == model.id
            )
        )
        if source_document is None:
            effective_date = (
                date.fromisoformat(release_date)
                if release_date
                else datetime.fromisoformat(downloaded_at).date()
            )
            source_document = SourceDocument(
                model_id=model.id,
                file_path=file_path,
                document_type=DocumentType.price_list,
                market=MARKET,
                locale=LOCALE,
                effective_date=effective_date,
                retrieved_at=datetime.fromisoformat(downloaded_at).replace(tzinfo=timezone.utc),
            )
            self._db.add(source_document)
            self._db.flush()
        self._source_document_cache[key] = source_document
        return source_document

    def upsert_price(
        self,
        configuration: Configuration,
        source_document: SourceDocument,
        amount: float,
        currency: str,
        valid_from: str,
    ) -> None:
        """Inserts a new current-price row for `configuration`, closing
        out the previous one - unless the current row already matches
        (no-op) or `valid_from` would rewrite history backwards (also a
        no-op). Updates `self.stats.prices_inserted`/`prices_unchanged`.

        Args:
            configuration: The configuration this price is for.
            source_document: The document this price was read from.
            amount: New price amount (used for both `list_price` and
                `price_incl_vat` - scraper doesn't distinguish them).
            currency: New price's currency.
            valid_from: New price's effective date (`YYYY-MM-DD`).
        """
        valid_from_date = date.fromisoformat(valid_from)
        current = self._db.scalar(
            select(Price).where(
                Price.configuration_id == configuration.id,
                Price.market == MARKET,
                Price.valid_to.is_(None),
            )
        )
        if current is not None:
            if (
                float(current.price_incl_vat) == amount
                and current.currency == currency
                and current.valid_from == valid_from_date
            ):
                self.stats.prices_unchanged += 1
                return
            if valid_from_date <= current.valid_from:
                # Stale/out-of-order data (e.g. reprocessing an older
                # document) - never rewrite history backwards.
                self.stats.prices_unchanged += 1
                return
            current.valid_to = valid_from_date

        self._db.add(
            Price(
                configuration_id=configuration.id,
                source_document_id=source_document.id,
                market=MARKET,
                currency=currency,
                list_price=amount,
                price_incl_vat=amount,
                valid_from=valid_from_date,
                valid_to=None,
                scraped_at=datetime.now(timezone.utc),
            )
        )
        # SessionLocal is autoflush=False (see app/db/session.py) - flush
        # now so the next call's `current = self._db.scalar(select(Price)
        # ...)` above actually sees this row. Without it, two scraper
        # variants that collapse into the same configuration in the same
        # run (the source PDFs do contain exact duplicate rows - e.g.
        # Škoda Scala's "Top Selection 1,0 TSI/85 kW" appears twice) would
        # both pass the "no current price yet" branch and violate the
        # partial unique index on the second insert.
        self._db.flush()
        self.stats.prices_inserted += 1

    def get_or_create_option_item(self, model: CarModel, name: str) -> OptionItem:
        """Args:
            model: The option item's model (`option_items.model_id` FK).
            name: Display name (see `humanize_equipment_name`) - the
                natural key together with `model`, since `option_items`
                has no DB-level uniqueness of its own.

        Returns:
            The existing `OptionItem` row for `(model, name)`
            (`category` always `equipment` - this importer only ever
            creates equipment rows, never packages/warranties/service),
            or a newly created one.
        """
        key = (model.id, name)
        if key in self._option_item_cache:
            return self._option_item_cache[key]
        option_item = self._db.scalar(
            select(OptionItem).where(OptionItem.model_id == model.id, OptionItem.name == name)
        )
        if option_item is None:
            option_item = OptionItem(model_id=model.id, category=OptionCategory.equipment, name=name)
            self._db.add(option_item)
            self._db.flush()
        self._option_item_cache[key] = option_item
        return option_item

    def upsert_option_availability(
        self,
        configuration: Configuration,
        option_item: OptionItem,
        availability: AvailabilityStatus,
        surcharge_amount: float | None,
        currency: str | None,
    ) -> None:
        """Inserts or updates the `(option_item, configuration)` row -
        unlike `upsert_price`, this isn't append-only (option_availability
        has no history concept), so an existing row is updated in place
        rather than closed out. Updates
        `self.stats.option_availabilities_inserted/updated/unchanged`.

        Args:
            configuration: The configuration this availability is for.
            option_item: The option item this availability is for.
            availability: Mapped drivewise status (see
                `_SCRAPER_TO_AVAILABILITY_STATUS`).
            surcharge_amount: Price in CZK, or `None` (only set for
                `optional` - see the CHECK constraint on
                `app/models/option_availability.py`).
            currency: `"CZK"` when `surcharge_amount` is set, else `None`.
        """
        existing = self._db.scalar(
            select(OptionAvailability).where(
                OptionAvailability.option_item_id == option_item.id,
                OptionAvailability.configuration_id == configuration.id,
            )
        )
        if existing is not None:
            existing_surcharge = float(existing.surcharge_amount) if existing.surcharge_amount is not None else None
            if (
                existing.availability == availability
                and existing_surcharge == surcharge_amount
                and existing.currency == currency
            ):
                self.stats.option_availabilities_unchanged += 1
                return
            existing.availability = availability
            existing.surcharge_amount = surcharge_amount
            existing.currency = currency
            self.stats.option_availabilities_updated += 1
            return

        self._db.add(
            OptionAvailability(
                option_item_id=option_item.id,
                configuration_id=configuration.id,
                availability=availability,
                surcharge_amount=surcharge_amount,
                currency=currency,
            )
        )
        # Flush now for the same reason as upsert_price above: two scraper
        # variants can collapse into the same configuration within one run
        # (duplicate source rows), and SessionLocal is autoflush=False - so
        # a second call for the same (option_item, configuration) within
        # this run must see this insert via the `existing = ...` select
        # above, not violate the UNIQUE constraint on a blind second insert.
        self._db.flush()
        self.stats.option_availabilities_inserted += 1

    def import_equipment(self, model: CarModel, configuration: Configuration, variant_id: int) -> None:
        """Imports every `equipment_assignment` row for one scraper
        `variant_id` into `option_items`/`option_availability` for
        `configuration` - skipping rows this importer can't represent
        without fabricating data (see module docstring). Updates
        `self.stats.equipment_skipped`.

        Args:
            model: The variant's model (`option_items.model_id` FK).
            configuration: The variant's already-resolved configuration.
            variant_id: scraper's `variant.id` to read equipment_assignment for.
        """
        rows = self._scraper_con.execute(
            "SELECT e.canonical_name, ea.availability, ea.surcharge_amount, ea.currency "
            "FROM equipment_assignment ea JOIN equipment e ON e.id = ea.equipment_id "
            "WHERE ea.variant_id = ?",
            (variant_id,),
        ).fetchall()

        for canonical_name, scraper_availability, surcharge_amount, currency in rows:
            availability = _SCRAPER_TO_AVAILABILITY_STATUS.get(scraper_availability)
            if availability is None:
                # PACKAGE - no equivalent drivewise state yet.
                self.stats.equipment_skipped += 1
                continue
            if availability == AvailabilityStatus.optional and surcharge_amount is None:
                # No price to satisfy the 'optional' CHECK constraint -
                # can't fabricate one.
                self.stats.equipment_skipped += 1
                continue

            option_item = self.get_or_create_option_item(model, humanize_equipment_name(canonical_name))
            self.upsert_option_availability(
                configuration,
                option_item,
                availability,
                float(surcharge_amount) if surcharge_amount is not None else None,
                currency,
            )

    def run(self) -> ImportStats:
        """Imports every document/variant/price from `scraper_con` into
        `db`, via the `get_or_create_*`/`upsert_price` methods above.
        Does not commit or roll back - the caller (see `main`) owns the
        transaction boundary.

        Returns:
            `self.stats`, fully populated (also available as `self.stats`
            immediately after this returns, for callers that want it
            without capturing the return value).
        """
        documents = self._scraper_con.execute(
            "SELECT id, source_brand, file_path, release_date, downloaded_at FROM document"
        ).fetchall()

        for doc_id, source_brand, file_path, release_date, downloaded_at in documents:
            variants = self._scraper_con.execute(
                "SELECT id, model, trim, powertrain, variant_name FROM variant WHERE document_id = ?",
                (doc_id,),
            ).fetchall()
            if not variants:
                continue

            brand = self.get_or_create_brand(source_brand)

            # Most scraper documents cover exactly one model, but not all -
            # Mercedes-Benz's combined price list covers several
            # (C-Class/C-Class Estate/E-Class/E-Class Estate all come out
            # of the same PDF, see parsers/mercedes_benz.py) - so variants
            # are grouped by their own `model` value rather than assuming
            # the whole document shares `variants[0][1]`. Each group gets
            # its own `SourceDocument` row sharing the same `file_path`
            # (see get_or_create_source_document's `(file_path, model)`
            # natural key).
            variants_by_model: dict[str, list] = {}
            for variant_row in variants:
                variants_by_model.setdefault(variant_row[1], []).append(variant_row)

            for model_name, model_variants in variants_by_model.items():
                model = self.get_or_create_model(brand, model_name)
                source_document = self.get_or_create_source_document(
                    model, file_path, release_date, downloaded_at
                )

                for variant_id, _model_name, trim_name, scraper_powertrain, variant_name in model_variants:
                    trim = self.get_or_create_trim(model, trim_name)

                    fuel_type = infer_fuel_type(scraper_powertrain, variant_name)
                    drivetrain = infer_drivetrain(variant_name)
                    power_kw = extract_power_kw(variant_name)
                    signature = powertrain_signature(variant_name, trim_name)
                    powertrain = self.get_or_create_powertrain(
                        model, signature, fuel_type, drivetrain, power_kw
                    )
                    configuration = self.get_or_create_configuration(trim, powertrain)

                    price_row = self._scraper_con.execute(
                        "SELECT price, currency, valid_from FROM price_history "
                        "WHERE variant_id = ? ORDER BY valid_from DESC LIMIT 1",
                        (variant_id,),
                    ).fetchone()
                    if price_row is not None:
                        amount, currency, valid_from = price_row
                        self.upsert_price(configuration, source_document, amount, currency, valid_from)

                    self.import_equipment(model, configuration, variant_id)

        self.stats.brands = len(self._brand_cache)
        self.stats.models = len(self._model_cache)
        self.stats.trims = len(self._trim_cache)
        self.stats.powertrains = len(self._powertrain_cache)
        self.stats.configurations = len(self._configuration_cache)
        self.stats.source_documents = len(self._source_document_cache)
        self.stats.option_items = len(self._option_item_cache)
        return self.stats


def main() -> None:
    """CLI entry point: parses `--dry-run`, runs one `ScraperDataImporter`
    pass, commits (or rolls back for `--dry-run`), and prints the summary.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run", action="store_true", help="Run the import but roll back instead of committing."
    )
    args = parser.parse_args()

    if not SCRAPER_DB_PATH.exists():
        raise SystemExit(f"scraper DB not found at {SCRAPER_DB_PATH} - run the scraper first.")

    scraper_con = sqlite3.connect(SCRAPER_DB_PATH)
    db = SessionLocal()
    try:
        importer = ScraperDataImporter(db, scraper_con)
        stats = importer.run()
        if args.dry_run:
            db.rollback()
        else:
            db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
        scraper_con.close()

    print(f"{'[DRY RUN] ' if args.dry_run else ''}Import summary:")
    print(f"  brands: {stats.brands}, models: {stats.models}, trims: {stats.trims}")
    print(f"  powertrains: {stats.powertrains}, configurations: {stats.configurations}")
    print(f"  source_documents: {stats.source_documents}")
    print(f"  prices: {stats.prices_inserted} inserted, {stats.prices_unchanged} already up to date")
    print(
        f"  option_items: {stats.option_items}, option_availability: "
        f"{stats.option_availabilities_inserted} inserted, "
        f"{stats.option_availabilities_updated} updated, "
        f"{stats.option_availabilities_unchanged} already up to date"
    )
    print(
        f"  equipment_assignment rows skipped (PACKAGE, or OPTIONAL with no price): "
        f"{stats.equipment_skipped}"
    )


if __name__ == "__main__":
    main()

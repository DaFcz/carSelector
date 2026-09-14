---
name: drivewise-scraper
description: The web-scraping data-collection service (scraper/) for DriveWise AI that downloads manufacturer PDF price lists (or, for Audi, a JSON API response, or for Tesla, an HTML configurator page - see `content_type`), parses variants/prices/equipment via per-brand plugin parsers, and stores them in its own SQLite/Postgres database (document/variant/price_history/equipment). Use this whenever building or changing anything under scraper/ — discoverers, parsers, downloaders, normalization, or the ScraperPipeline. Reach for it any time a task involves pulling car data from manufacturer sites or PDF price lists, adding a new brand/model, or verifying extracted data against a source document.
---

# DriveWise AI — Web Scraping Service (`scraper/`)

A standalone Python service, independent of `backend/`. It runs **offline, outside the request
path**: for every active source in `scraper/config/sources.yaml`, it discovers new/changed PDF
price lists, downloads them, parses variants/prices/(optional) equipment, and stores the result in
its own database — `storage/scraper.db` (SQLite by default; swappable via
`SCRAPER_DATABASE_URL`). Entry point: `python -m scraper.main` (`ScraperPipeline`).

**This is a different schema from `backend`'s catalog** (see `drivewise-data-model`) — there is no
*live* import step between them. Don't assume scraped data automatically appears in the backend
API; verify against `storage/scraper.db` (e.g. via Datasette) instead. A manual/periodic batch
import does exist (`scripts/import_scraper_data.py`, repo root) - after a scrape, run it to load
new/changed data into the backend's catalog; it's not triggered automatically by `python -m
scraper.main`.

## Pipeline

```
sources.yaml → SourceMonitor (discoverers) → PdfDownloader/JsonDownloader/HtmlDownloader → per-brand Parser → EquipmentNormalizer → scraper.db
```

`Source.content_type` ("pdf", default, "json", or "html") picks the downloader and tells
`ScraperPipeline` whether to run the PDF-only release-date extraction step. Audi is the only
"json" source so far (its data comes from its web configurator's own API, not a downloadable price
list) — see `parsers/audi.py`'s module docstring. Tesla is the only "html" source (its data is
embedded in its own web configurator page's HTML, with no separate API to call) — see
`parsers/tesla.py`'s module docstring. Tesla's own source is registered but `active: false` — see
that source's own comment in `sources.yaml` for why (tesla.com blocks the scraper's fetch
mechanism outright, unlike every other brand's own bot-protection here).

## Schema (`scraper/database/models.py`)

```
document     id, source_brand, document_url, sha256_hash (dedup), file_path, release_date,
             downloaded_at

variant      id, document_id → document, brand, powertrain ("ICE"/"EV"), model, trim,
             variant_name, source_page, raw_text
             — source_page + raw_text make every value traceable back to the exact PDF text

price_history  id, variant_id → variant, document_id → document, price, currency, valid_from

equipment    id, canonical_name (unique)  — normalized name, see normalization/equipment_alias.py

equipment_assignment  id, variant_id → variant, equipment_id → equipment,
             availability (STANDARD/OPTIONAL/PACKAGE/NOT_AVAILABLE)
```

Every `Variant`/`PriceHistory` row links back to `document.source_page` + `raw_text` by design —
extraction can always be verified against the source, not trusted blindly.

## Plugin architecture — adding a brand/model

Each layer is a registry of per-brand plugins, so adding a brand touches only new files:
1. `scraper/monitors/discovery/<brand>.py` — a `BaseDiscoverer` subclass that finds the PDF link(s) on the OEM's page; register in `monitors/discovery/registry.py`.
2. `scraper/parsers/<brand>.py` — a `BaseParser` subclass matching that brand's PDF layout; register in `parsers/registry.py`.
3. An entry in `scraper/config/sources.yaml` (`source_url`, `pdf_pattern`, `active: true`).

Existing brands (Škoda, VW, Kia, Toyota — ICE/EV/MHEV/HEV/PHEV as applicable) are the reference
implementations; see `doc/arch/webScraping/IMPLEMENTATION_PLAN.md` for current status and the
"vertical slice, then generalize" rollout order, and `doc/arch/webScraping/Car_Price_List_Architecture.md`
for the longer-term target (10 OEMs, Postgres, OCR fallback, LLM-assisted parsing).

## Code style

The plugin classes (`BaseParser`, `BaseDiscoverer`) already set the pattern — keep following it.
A new brand's parser/discoverer is exactly the kind of "real behavior grouped around state" that
belongs in a class, never a bag of loose functions (per `drivewise-architecture`'s Code style
section). Every `parse()`/`discover()` override, and every other method on a parser, discoverer,
or repository class, gets a docstring documenting its parameters and return value (Google-style
`Args:`/`Returns:`) — not just a one-line summary.

## Cleaning conventions

- `EquipmentNormalizer` (`scraper/normalization/`) unifies equipment names across brands into one canonical set — map source-specific aliases onto it rather than storing brand-specific strings.
- Dedup documents by `sha256_hash` per brand, not URL — OEMs replace PDF content at the same URL.
- Kia/Toyota price lists don't carry a release date the current date-extraction logic understands, so their variants use the download date as `valid_from` rather than a source-stated effective date — a known, accepted gap, not a bug to silently "fix" by guessing.

## Verifying data

- `pytest scraper/tests/ -v` — tests run against real PDF fixtures with values transcribed by hand, not derived from the parser.
- `python -m scraper.verification.review_cli --document-id <ID>` — prints every extracted variant next to its source `raw_text`.
- Datasette (`datasette storage/scraper.db --metadata scraper/tools/datasette_metadata.json`) for browsing/faceting the whole DB.

## Operational notes

- Runs are idempotent/re-runnable by design (hash-based dedup on `document`, not blind-insert).
- Kept free of `backend/` imports — it's a fully standalone service, importable and runnable on its own even though its Python dependencies now live in the repo-root `requirements.txt` alongside `backend/`'s (see `scraper/README.md`).

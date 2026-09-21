# Changelog

All notable changes to DriveWise AI (car selector) are documented here, grouped
into versions reconstructed from the git history. Newest version first.

## Versioning scheme

Internal versions use `0.y.z`:

- The leading **`0`** is fixed for the whole pre-public-release phase. Public
  releases will start at `1.x.x`; the `0.` prefix is reserved so it never
  collides with those.
- **`y`** (major) increments on a *big* change — a technology switch or a
  fundamental shift in how the system is built (e.g. replacing the Node.js/
  React frontend with a pure-Python UI).
- **`z`** (minor) increments for everything else — new features, new scraper
  brands, refactors, fixes, and documentation.

There are no `x.y.z-alpha`/build-number suffixes; each entry below corresponds
to one or more related commits.

---

## 0.2.34 — 2026-09-21

### Added
- Real email delivery for login codes. The SMTP sender from 0.2.33 had never
  been run against a mail server and, with `EMAIL_BACKEND` defaulting to
  `console`, nothing was actually emailed. It is now hardened and verified
  against a real socket (`tests/test_smtp_wire.py`: plain + auth, STARTTLS,
  implicit SSL, wrong password, rejected recipient, and a certificate that
  fails verification being refused before any credentials are sent):
  `Date`/`Message-ID`/`Auto-Submitted` headers, a display name
  (`SMTP_FROM_NAME`), a plain-text + HTML body, explicit envelope
  sender/recipient, and error messages that name the failure (never the code
  or password).
- `scripts/send_test_email.py you@example.cz`: sends one message through the
  configured backend to check a setup, with hints for the usual failures.
- Startup log of how codes are delivered (`log_email_backend_status`): a loud
  warning for the `console` backend, an error naming the problem for an
  incomplete `smtp` config, a warning for `SMTP_SECURITY=none` with a password.
- `backend/.env.example` with provider presets (Seznam, Gmail, transactional
  providers); README table and deliverability notes (SPF/DKIM).

### Changed
- The login dialog now says when the `console` backend is active that no
  email is sent and the code is in the server log, instead of "we sent you a
  code" for a mail that never arrives.
- `SMTP_PORT` defaults to the conventional port for `SMTP_SECURITY` (587 /
  465 / 25) instead of always 587; a blank `SMTP_PORT=` counts as unset.
- `SMTP_*` settings are validated together (`smtp_config_problem`): missing
  host/sender, malformed sender, unknown security mode, user without password.

## 0.2.33 — 2026-09-21

### Added
- Passwordless email login (`app/services/auth.py`, `app/ui/auth.py`,
  `app/ui/components/login_dialog.py`): the header's "Přihlásit se" opens a
  dialog where a person enters an email, receives a 6-digit code and types it
  in. Any address can create a regular account this way (the first successful
  login creates it); the catalog, chat and wizard stay usable without an
  account. Codes are single-use, expire after 10 minutes, are stored only as a
  keyed hash, are burned after 5 wrong guesses, and code requests are
  rate-limited per address and per IP. A session is re-checked against the
  database on every page load and expires after 30 days.
- `users` and `login_codes` tables (Alembic migration `a3f1c9d27b40`).
- Email delivery (`app/services/mailer.py`): `EMAIL_BACKEND=console` (default,
  prints the code to the server log - development only) or `smtp` (stdlib
  `smtplib`, `SMTP_*` settings; no new dependency).
- Admin rights: an address listed in `ADMIN_EMAILS` becomes an admin at its
  next login (grant-only; `users.is_admin` is the source of truth after that).
  All new settings are documented in `backend/README.md`'s Login section.

### Changed
- `/admin` (scraper and catalog-import console) and the header's "AI klíč"
  button/dialog are now **admin-only**. Previously any visitor could start the
  scraper subprocesses and replace the process-wide AI key. Anonymous visitors
  see a login prompt on `/admin`, regular accounts a "no admin rights" note;
  the page builds no privileged elements for them, and the API-key dialog
  re-checks admin rights in its handlers rather than relying on a hidden
  button. A rejected-API-key chat error now tells non-admins to contact the
  administrator instead of pointing at the button they can't see.
- `scripts/run.bat` runs `alembic upgrade head` before importing scraper data,
  so pulling this change picks up the new tables.
- `/api/*` is unchanged and still unauthenticated; login gates the UI only.

## 0.2.32 — 2026-09-20

### Added
- "AI klíč" button in the header (`app/ui/components/api_key_dialog.py`) that
  opens a dialog for entering the AI provider's API key (Groq by default per
  `AI_PROVIDER`) at runtime, so no key has to be written into source code or
  `.env`. The button is highlighted ("AI klíč chybí") while no key is set.
  The key is held in process memory only (`app.ai.client.set_runtime_api_key`),
  takes priority over the environment's key, is never shown back, and has to
  be re-entered after an app restart.

- `AiProviderError` (`app/ai/errors.py`): the `LlmClient` adapters now translate
  Anthropic/Groq SDK failures into provider-agnostic codes (`ai_invalid_key`,
  `ai_rate_limited`, `ai_model_unavailable`, `ai_unreachable`, `ai_error`).
  The chat and the wizard show a specific Czech message for each (e.g. "AI
  služba odmítla API klíč ..."), and `POST /api/conversations/{id}/messages`
  answers 502 with the same code.

### Changed
- Default `GROQ_MODEL` is now `openai/gpt-oss-120b`: Groq shut down the former
  default `llama-3.3-70b-versatile` on 2026-08-16, so every Groq call failed
  with "model not available". Because it is a reasoning model,
  `GroqLlmClient` sends `reasoning_effort="low"` and `include_reasoning=False`
  and adds headroom to `max_tokens` for `openai/gpt-oss*` models, so short
  answers (the 100-token explanation) aren't eaten by the thinking budget.

### Fixed
- The API-key dialog now rejects a key containing diacritics/non-ASCII
  characters or spaces (typically a typo or the wrong keyboard layout). Such
  a key used to reach the HTTP layer and crash it with a `UnicodeEncodeError`
  while building the `Authorization` header, before any request was sent -
  shown only as the generic error.
  The rejection names the offending character and its position (never the
  key), and the key field is `autocomplete=new-password` so browsers don't
  autofill a saved credential into it.
- A rejected/failed AI call used to surface only as the generic "Něco se
  nepovedlo" with nothing logged; `ConversationState` now logs the cause
  (`logging`) and reports the specific error code instead.
- `RequirementInterpreter`/`ExplanationGenerator` no longer cache the shared
  default client on first use, so a key entered or changed after the first AI
  call takes effect without restarting.

## 0.2.31 — 2026-09-18

### Added
- Equipment and color extraction for CUPRA (`cupra_equipment.py`), rewritten
  from scratch after 0.2.30 deleted the brand's first, badly-garbled attempt.
  Standard equipment comes from CUPRA's own "SÉRIOVÁ VÝBAVA" pages (a 2-4
  column newspaper grid told apart from category headings purely by font
  size, read in column-major order since one trim's own section can span
  several columns/pages without re-declaring itself); colors come from the
  "BARVY" pages (a Private-Use-Area included/priced-option glyph per trim
  column, same icon-font convention `peugeot_equipment.py` already found) and
  are folded into the same `equipment`/`equipment_surcharge` fields, since
  `ExtractedVariant` has no dedicated colors field. Verified against all six
  CZ models (Born, Formentor, Leon, Leon Sportstourer, Raval, Terramar) - see
  `scraper/tests/test_cupra_equipment.py`.
- `storage/scraper.db` backfilled for all six already-scraped CUPRA
  documents (local re-parse, no re-scrape) - 6,155 new
  `equipment_assignment` rows, then re-imported into `storage/drivewise.db`
  via `scripts/import_scraper_data.py`.

### Fixed
- `cupra.py`: Terramar's own price table calls its special editions "Tribe
  Edition"/"Tribe VZ Edition", but the SAME document's SÉRIOVÁ VÝBAVA
  headings drop the "Edition" suffix ("Tribe"/"Tribe VZ") - a genuine
  naming split within CUPRA's own PDF, not a parser bug. Without handling
  it, both trims silently got zero equipment items. `_resolve_equipment`
  now falls back to the suffix-stripped name when the exact trim name
  isn't found.

### Known limitation
- Raval's own "Akční model ROOKIE" special edition has no SÉRIOVÁ VÝBAVA
  section under any name in its source PDF - stays a genuine equipment gap
  (it still gets colors, from the BARVY page's own sequential trim
  consumption, which doesn't depend on the equipment page at all).
- A few CUPRA "BARVY" pages (e.g. Terramar's) carry an unexplained second
  glyph cluster far to the right of the real per-trim mark columns; excluded
  via a hardcoded x-position bound (`_MARK_MAX_X0`) rather than fully
  root-caused, so a handful of color rows on those specific pages may still
  be missing.

## 0.2.30 — 2026-09-17

### Added
- Equipment extraction for nine more scraper brands, following the same
  pattern 0.2.28 established for Dacia (`ExtractedVariant.equipment`/
  `equipment_surcharge`, no changes needed in `scripts/
  import_scraper_data.py`): Mazda (`mazda_equipment.py` - a checkbox
  matrix whose mark glyphs differ per fixture, read from each page's own
  legend line rather than hardcoded), Volkswagen ICE/EV (`vw_equipment.py`
  - a bold-title card grid, shared by both `volkswagen.py`/
  `volkswagen_ev.py`), Hyundai, MG, Opel, Kia, Renault (bullet-list or
  matrix pages, per brand), and Peugeot (`peugeot_equipment.py` - a
  checkbox/price hybrid matrix using a Private-Use-Area glyph for
  "included", with real per-trim option prices where the source states
  one). Fixes the reported case: Peugeot 208 GT (and every other Peugeot
  trim) showing no equipment at all - now 69 standard + 5 priced optional
  items for that specific trim.
- `storage/scraper.db` backfilled for all nine brands' already-scraped
  documents (local re-parse of already-downloaded PDFs, no re-scrape) -
  30,709 new `equipment_assignment` rows, then re-imported into `storage/
  drivewise.db` via the existing `scripts/import_scraper_data.py`
  (30,388 new `option_availability` rows).
- `scripts/run.bat` now runs `scripts/import_scraper_data.py` before
  starting the app, so the catalog picks up whatever `scraper/` has found
  since the last run automatically - a failure there (e.g. no `storage/
  drivewise.db` yet) doesn't block starting the server, it just leaves
  the catalog as it was.

### Fixed
- `peugeot_equipment.py`: an item name that legitimately recurs elsewhere
  on the same page (e.g. a paint option repeated per engine block) could
  end up written as `STANDARD` for one trim while an earlier pass had
  already recorded a price for that same name/trim - violating `option_
  availability`'s own "a price exists iff optional" CHECK constraint once
  imported. Setting `STANDARD` now always clears any stale price for that
  item name first.

### Removed
- CUPRA's and Ford's own equipment-extraction modules, added in the same
  work as the brands above: both produced badly garbled item names (their
  own multi-column word-clustering logic didn't handle these two brands'
  particular page layouts correctly - verified by hand, not a marginal
  quality gap) and were never wired into their parsers. Removed rather
  than shipped half-working or left as unused dead code; equipment
  extraction for these two brands is still an open gap, same status as
  BMW/Mercedes-Benz (no equipment section in the source PDF at all) and
  Audi/Tesla (JSON/HTML sources - see below).
- Stray debug-session output files that had been committed by mistake
  (`scratch_*.txt`, `*_out.txt` at the repo root).

### Known limitation
- Audi's scraped source (`konfigurator.audi.cz`'s modelgroup JSON API)
  carries no per-vehicle color or equipment catalog - only a single
  preselected paint code (for the configurator's own preview image) and,
  for a handful of variants, a warranty marketing blurb, not equipment
  features. Real color/equipment data would need a materially different,
  stateful per-model configurator API session this scraper doesn't
  currently fetch (investigated live via the actual konfigurator.audi.cz
  app - confirmed such a session-based flow exists behind its "Design"/
  "Výbava" steps, but reliably automating through it wasn't completed).

## 0.2.29 — 2026-09-17

### Changed
- `scripts/statistics.py` (the repo's own Python file/line-count tool):
  scan root no longer hardcoded to a local machine path, now resolved from
  the script's own location; excludes `.venv`/`.git`/caches so third-party
  code doesn't skew the numbers; output broken down per top-level directory
  with a size column (B/KB/MB/GB) alongside file/line counts; added
  `scripts/statistics.bat` wrapper.

## 0.2.28 — 2026-09-14

### Added
- Equipment extraction in the Dacia scraper parser (`scraper/parsers/
  dacia_equipment.py`): every Dacia model's price list has its own
  "Hlavní prvky sériové výbavy" page listing each trim's standard
  equipment - either as that trim's complete list, or (Sandero, Sandero
  Stepway, Spring, Jogger) as a delta "navíc oproti <nižší trim>" on top
  of a lower trim's list. `DaciaParser` now reads this page once per
  document and attaches the right per-trim set to each `ExtractedVariant`
  (all `STANDARD` - Dacia's price lists have no priced a-la-carte options),
  the same generic `ExtractedVariant.equipment` field every parser can
  populate - `scripts/import_scraper_data.py` needed no changes.
  Fixes: Dacia vehicles (e.g. "Sandero Expression", "Sandero Stepway
  Extreme") showing no equipment at all in the vehicle detail view.
- `storage/scraper.db` backfilled with equipment for the 6 Dacia
  documents already scraped before this parser change (re-parsed their
  already-downloaded PDFs locally, no re-scrape) - 1,710 new
  `equipment_assignment` rows, then re-imported into `storage/
  drivewise.db` via the existing `scripts/import_scraper_data.py`.

## 0.2.27 — 2026-09-14

### Added
- Volkswagen Tiguan as a second real, hand-verified vehicle in
  `app.db.seed.seed_demo_data()` (`backend/app/db/seed.py`), alongside the
  existing Mazda CX-5 - People/R-Line People trims, one FWD diesel and one
  AWD petrol configuration, all figures (prices, tech specs, paint codes,
  optional-equipment surcharges) read from
  `storage/cars/vw/tiguan/Akcni_Tiguan_People_01_07_2026_new_cover_new.pdf`.
- Real colors and per-trim equipment for the Mazda CX-5 seed, replacing the
  previous single placeholder color/option: all 7 paint options from the
  brochure's "NABÍDKA BAREV KAROSERIE" table and ~70 real standard-equipment
  items per trim from its VÝBAVA tables (audio, exterior, interior, safety,
  comfort) - both configurations now exercise the vehicle detail modal's
  colors/standard-equipment sections with real brochure data instead of a
  single fabricated row each.
- VW's optional equipment (wheels, lighting packages, upholstery,
  warranty/service packages) seeded with real Kč surcharges, so the
  detail modal's "Volitelná výbava" section - previously always empty in
  the demo data - now shows real priced options for the first time.

### Changed
- `SeededData` (`backend/app/db/seed.py`, mirrored in
  `backend/tests/conftest.py`) gained `vw_model_id`/`config_people_fwd_id`/
  `config_rline_awd_id` alongside the existing Mazda fields.
- Catalog-level tests (`test_catalog_api.py`, `tests/ui/test_state.py`)
  updated for the now 2-brand/4-configuration seeded catalog; the
  `Color.finish_type` on Mazda's colors moved from a hardcoded `solid` to
  `None`, matching the brochure (which states no finish per color, unlike
  VW's explicit solid/metallic/pearlescent categorization).

## 0.2.26 — 2026-09-14

### Added
- Tesla support in the scraper: discovery + parser for Tesla's whole
  current CZ lineup - Model Y and Model 3, the only two models sold here
  (Model S/X have no CZ configurator page) - 4 trims each (base RWD,
  "Premium" Long Range RWD/AWD, "Performance" AWD), all EV
  (`scraper/parsers/tesla.py`, `scraper/monitors/discovery/tesla.py`),
  with real fixtures and parser tests. Like Audi, Tesla has no
  downloadable price-list PDF; unlike Audi, it also has no separately-
  callable JSON API - the data is embedded in its own web configurator
  ("Design Studio") page's own HTML, extracted via a balanced-brace scan
  for the `"Lexicon.<model>":` key rather than parsing the page's own
  `dataJson` wrapper as a whole (which isn't strict JSON).
- Generalized the scraper pipeline with a third `content_type`: `"html"`
  alongside `"pdf"`/`"json"`, with a new `HtmlDownloader` mirroring
  `PdfDownloader`/`JsonDownloader`'s hash-based storage.
  `SourceMonitor`/`ScraperPipeline` route Tesla's own source through it
  the same way Audi's `"json"` one already works. No changes needed for
  any existing brand.
- Broadened `scripts/import_scraper_data.py`'s drivetrain detection for
  Tesla's own Czech wording: `_RWD_RE` now matches "zadní"'s inflected
  forms (e.g. "zadních", not just the bare word MG's price tables use),
  and `_AWD_RE` gained a "všech kol" alternative.

### Known limitation
- Tesla's `sources.yaml` entry is registered but `active: false`, unlike
  every other brand here - every tesla.com path returns a 403 from
  Akamai's bot protection for a bare `requests.get()` (even with a full
  browser header set) and for a vanilla Playwright browser (headless or
  headed) alike, from this environment. The parser itself is complete and
  verified against real Design Studio pages saved through an interactive
  browser session that wasn't blocked; flipping the source to
  `active: true` needs a working unattended fetch path first (see
  `doc/arch/webScraping/IMPLEMENTATION_PLAN.md`).

## 0.2.25 — 2026-09-14

### Added
- Audi support in the scraper: discovery + parser for Audi's entire
  current CZ lineup - 22 model groups, 110 model/engine rows across
  base and "S line" trims plus S/RS performance models
  (`scraper/parsers/audi.py`, `scraper/monitors/discovery/audi.py`), with
  a real fixture and parser tests. Audi is the first brand here with no
  downloadable price-list PDF at all - its data comes from its own web
  configurator's JSON API instead, reachable directly with `requests`.
- Generalized the scraper pipeline to support a non-PDF source: `Source`
  gained a `content_type` field (`"pdf"` by default, `"json"` for Audi),
  a new `JsonDownloader` mirrors `PdfDownloader`'s hash-based storage for
  JSON responses, `SourceMonitor` picks the matching downloader per
  source, and `ScraperPipeline` skips the PDF-only release-date
  extraction step for non-PDF sources. No changes needed for any
  existing brand (`content_type` defaults to `"pdf"`).

## 0.2.24 — 2026-09-13

### Added
- MG support in the scraper: discovery + parser for MG's full current CZ
  lineup - MG3, MGS9 PHEV, MG ZS, MG HS, MG4 EV Urban, MGS5 EV, MG
  Cyberster (`scraper/parsers/mg.py`, `scraper/monitors/discovery/mg.py`),
  with PDF fixtures and parser tests. mgmotor-czech.cz has no bot-blocking
  (unlike Opel/Peugeot), so discovery is a plain single-page scrape.
  Widened `_pdf_layout.extract_release_date`'s regex ("Platnost ceníku
  od ..." vs the usual "Platnost od ...") so MG's own release dates are
  captured instead of falling back to the download date. Added RWD
  detection to `scripts/import_scraper_data.py`'s `infer_drivetrain` (MG
  is the first brand here to print drivetrain per row plainly enough to
  read "zadní"/rear directly).

## 0.2.23 — 2026-09-13

### Added
- Peugeot support in the scraper: discovery + parser for 208, 2008,
  308 SW, 3008, 408, 5008 and Rifter (`scraper/parsers/peugeot.py`,
  `scraper/monitors/discovery/peugeot.py`), with PDF fixtures and parser
  tests. peugeot.cz's own listing page is Akamai-blocked like Opel's, but
  the real PDFs live on an unblocked flipbook-viewer site
  (peugeot.ecpaper.cz), so `PeugeotDiscoverer` resolves each model's
  current PDF live instead of hardcoding it. Added `HDi` to
  `scripts/import_scraper_data.py`'s diesel regex (BlueHDi's own badge).

## 0.2.22 — 2026-09-13

### Added
- Opel support in the scraper: discovery + parser for the current CZ
  personal-car lineup - Corsa, Astra (hatchback and Sports Tourer body
  styles), Mokka, Frontera and Grandland, each with its own combustion/
  hybrid document plus its own separate all-electric document (Combo/
  Vivaro/Movano commercial vehicles are out of scope) - with PDF test
  fixtures and parser tests (`scraper/monitors/discovery/opel.py`,
  `scraper/parsers/opel.py`). Opel's own price table is a genuine column
  grid (trim/LCDV code/engine/fuel/transmission/price), closer to Ford's
  matrix shape than Kia's/Renault's plain trim-heading list, with its own
  set of column-position pitfalls not seen in Ford's own table (a
  vertically-merged trim cell spanning several engine rows; wrapped
  engine/transmission text split across the row's own baseline; wide
  values in some columns starting past a naive midpoint boundary in either
  direction) - see `OpelParser`'s module docstring for how each is solved.
- Unlike every other brand here, opel.cz's own listing page can't be
  fetched automatically at all - it sits behind an Akamai WAF blocking at
  the TLS/network-fingerprint level, not just on missing headers (verified
  even Windows' own curl.exe gets blocked the same way on endpoints
  Python's `requests` gets through on). `OpelDiscoverer` hardcodes the
  current 11 document URLs directly instead; `scripts/
  download_opel_pricelists.py` (plus a thin `.bat` wrapper for a
  non-technical manual re-fetch) exists to re-download them by hand once
  the URLs eventually go stale (the path embeds a quarter marker that will
  presumably roll over) - see both modules' own docstrings.
- Wired Opel data into `scripts/import_scraper_data.py`: brand display
  name, and a new `CDTI` alternative in the diesel-detection regex (Opel/
  Stellantis's own diesel badge, not covered by the existing TDI/CRDI/
  BMW-style-suffix patterns) - the existing AWD regex already matched
  Opel's own "4x4" marker, no fix needed there.

## 0.2.21 — 2026-09-12

### Added
- Renault support in the scraper: discovery + parser for the full current
  CZ personal-car lineup - Clio, Captur, Symbioz, Arkana, Austral, Espace,
  Rafale, plus the electric Twingo, Renault 4, Renault 5, Megane and
  Scenic (Kangoo/Trafic/Master commercial vehicles are out of scope) -
  with PDF test fixtures and parser tests
  (`scraper/monitors/discovery/renault.py`, `scraper/parsers/renault.py`).
  Renault shares its parent Renault Group's own CDN with Dacia
  (cdn.group.renault.com), but its own price-list template reads like
  Kia's (a trim heading, then one row per engine) rather than Dacia's;
  row shape varies even within Renault's own documents (Twingo's price
  list omits the promotional-price column entirely, 2 trailing numeric
  columns instead of every other document's 3) - `RenaultParser` counts
  the trailing all-digit columns per row rather than assuming a fixed
  count. "Renault 4"/"Renault 5" are stored as bare `model` values ("4"/
  "5", matching the brand+model+trim display convention) - sources.yaml
  quotes them in the `models` list, learning from the exact bug an
  unquoted Mazda "3" caused earlier (see 0.2.9's Fixed entry).
- Wired Renault data into `scripts/import_scraper_data.py` (brand display
  name; Rafale's own "4×4" AWD marker and diesel markers already matched
  the existing regexes, no fixes needed there).

## 0.2.20 — 2026-09-12

### Added
- CUPRA support in the scraper: discovery + parser for Leon, Leon
  Sportstourer, Formentor, Terramar, Born and Raval - 6 of CUPRA's 8
  current CZ nameplates (Ateca is sold stock-only and Tavascan isn't yet
  on sale in CZ, so neither has a price list of its own to scrape), with
  PDF test fixtures and parser tests
  (`scraper/monitors/discovery/cupra.py`, `scraper/parsers/cupra.py`).
  CUPRA's price lists read like Kia's (a trim heading, then one row per
  engine) rather than Ford's column matrix; some documents (Leon,
  Formentor, Terramar) hold a second full price table further into the
  same PDF for a special edition ("Tribe", "VZ5", "Tribe Edition") -
  `CupraParser` reads every such table on a page-by-page basis rather than
  assuming one table per document. `release_date` still isn't populated
  (falls back to the download date, like every other brand added so far),
  but for a new reason: CUPRA's own disclaimer text would actually satisfy
  the shared `extract_release_date` helper's date-format pattern, it's
  just on the price-table page rather than the cover page that helper
  reads.
- Wired CUPRA data into `scripts/import_scraper_data.py` (brand display
  name; `infer_drivetrain`'s AWD regex didn't recognize CUPRA's own "4WD"
  marker, e.g. "2.0 TSI 204k DSG 4WD" - same class of gap as Dacia's
  "4×4" and BMW's "xDrive").

## 0.2.19 — 2026-09-07

### Fixed
- The wizard (and chat) still only ever showed 10 results, even once
  0.2.18 fixed the single-brand-monoculture bug - reported: a 1,000,000 Kč
  budget-only wizard answer showed 10 cars when 462 actually matched.
  `RecommendationEngine.recommend()`'s `limit` now defaults to `None` (no
  truncation) - a hard constraint like budget isn't something to
  additionally cap on top of. The real reason a cap existed at all -
  bounding how many per-vehicle AI explanation calls one chat/wizard turn
  makes (`ExplanationGenerator.explain` is its own Claude API call) - is
  now `ConversationOrchestrator.EXPLANATION_LIMIT` (10) instead: every
  match is still returned, but only the top 10 get an AI-generated
  explanation sentence (`VehicleSummary.explanation` is already optional
  and the card only renders that line when it's set).
- `app/ui/pages.py`'s results column only ever rendered the narrowed
  (AI/wizard) result list in one shot, unlike browsing mode's paginated
  "load more" - fine at 10 results, not at several hundred: rendering all
  462 at once would have reintroduced the ~650-700-card NiceGUI websocket
  message-size disconnect the 0.2.14 infinite-scroll fix addressed for
  browsing. Narrowed mode's infinite scroll now reveals more of the
  already-in-memory `conv.cars` list client-side (`_NarrowedPaging`, same
  `append_car_cards` mechanism as browsing's page fetches, just without a
  network round-trip) instead of being disabled outright.

## 0.2.18 — 2026-09-07

### Fixed
- The wizard (and chat) could return results from a single brand only,
  even for a wide, single-constraint filter like "budget up to 1,000,000
  Kč" (reported: only Škoda came back). `RecommendationEngine.recommend()`
  capped its candidate pool at `catalog.list_vehicles(..., page_size=100)`
  with no explicit `sort`, which defaults to `configuration.id` ascending;
  since ids are assigned in scrape/import order and Škoda was the first
  brand ever imported (186 configurations), any budget filter narrow
  enough to leave >=100 Škoda matches silently excluded every other brand
  from scoring entirely, regardless of how well - or how much more
  cheaply - they'd have matched. The candidate pool is now effectively the
  whole catalog (`CANDIDATE_POOL_SIZE = 5000`, comfortably above the
  current ~939 configurations) sorted by price ascending, so a future cap
  overflow degrades to "missing the priciest matches" rather than a
  single-brand monoculture. Added `backend/tests/test_recommendation_engine.py`,
  which reproduces the exact failure shape (a low-id, higher-priced brand
  crowding out a cheaper, higher-id one) as a regression test.

## 0.2.17 — 2026-09-07

### Added
- Ford support in the scraper: discovery + parser for Puma, Kuga, Mustang
  and Bronco, with PDF test fixtures and parser tests
  (`scraper/monitors/discovery/ford.py`, `scraper/parsers/ford.py`). Ford's
  price lists are a genuine trim x engine price matrix (column = trim,
  row = engine/transmission, each cell holding a discounted-with-financing
  price and a base list price) — structurally unlike every other brand's
  parser here, which reads a one-column list of trim headings with engine
  rows underneath. Only 4 of Ford's ~10-model current CZ lineup are
  covered — Explorer/Puma Gen-E/Mustang Mach-E (electric, an extra
  per-trim "Dojezd"/range column breaks this parser's column model),
  Tourneo Courier/Connect/Custom (a different "AKČNÍ CENÍK" bez/s DPH
  layout), Puma ST (a "Benzín" header this parser doesn't recognize) and
  Capri (unreachable from this environment) are a known gap for a
  follow-up, documented in `parsers/ford.py`'s module docstring rather
  than silently mis-parsed.
- Wired Ford data into `scripts/import_scraper_data.py` (brand display
  name; Kuga's "AWD" drivetrain marker already matched the existing AWD
  regex, no fix needed there).

## 0.2.16 — 2026-09-07

### Fixed
- The manufacturer/engine-type/drivetrain filter row scrolled away with
  the results, instead of staying visible while browsing the catalog.
  `app/ui/pages.py`'s single `results()` refreshable rendered the title/
  sort/filters and the card grid as one block inside the same scrollable
  column; it's now split into `results_header()` (title, sort control,
  filter_bar - a `shrink-0` sibling *outside* the scrollable column) and
  `results_body()` (loading/error state, the card grid - the only part
  that still scrolls, in its own `overflow-y-auto` column). A new
  `refresh_results()` helper refreshes both halves together at every call
  site that used to refresh the old single `results` (filter/sort
  changes, restart, wizard completion, chat turns); the infinite-scroll
  handler's own fallback re-render now targets `results_body()` alone,
  since loading another page never changes the title/count or filters.

## 0.2.15 — 2026-09-07

### Added
- Dacia support in the scraper: discovery + parser for the full current CZ
  lineup (Spring, Sandero, Sandero Stepway, Jogger, Duster, Bigster — one
  PDF price list per model, unlike Škoda/BMW's single combined listing),
  with PDF test fixtures and parser tests
  (`scraper/monitors/discovery/dacia.py`, `scraper/parsers/dacia.py`).
  Jogger's price list holds two full tables on one page (5-seat and 7-seat
  versions of the same trim/engine lineup); the seat count is folded into
  each variant's name so the two tables' otherwise-identical rows don't
  collapse into each other on import.

### Fixed
- `scripts/import_scraper_data.py`'s `infer_drivetrain` only matched a
  literal "4x4" AWD marker — Dacia's own "4×4" (Duster/Bigster's hybrid
  4×4 trims) uses the real multiplication sign (U+00D7), not the letter
  "x", so those variants were silently defaulting to FWD.

## 0.2.14 — 2026-09-06

### Fixed
- Infinite-scroll catalog browsing no longer disconnects the client once
  enough pages accumulate. Each scroll-triggered page load previously
  called `results.refresh()`, which (per `@ui.refreshable`'s "delete
  everything and recreate" semantics) re-rendered and re-sent *every*
  card loaded so far, not just the new page - at ~1.5 KB/card this
  crosses NiceGUI's ~1MB websocket message limit around 650-700
  accumulated cards, which the real catalog's 815 rows reliably hit,
  producing a "Message too long" popup followed by "Connection lost."
  `results_grid()` now returns its card container and a new
  `append_car_cards()` (`app/ui/components/results_grid.py`) appends only
  the newly-fetched page into it; `app/ui/pages.py`'s `on_results_scroll`
  uses this for the common case and falls back to a full
  `results.refresh()` only for the "Moje pořadí" custom-drag-order sort,
  whose `make_sortable` wiring is set up once per full render. Verified
  by scrolling the full 815-row catalog with no errors (previously
  reproducible around card ~700).

## 0.2.13 — 2026-09-06

### Added
- Guided step-by-step wizard as a non-technical alternative to the free-text
  chat, opened via a new "Průvodce výběrem" header button
  (`app/ui/components/wizard.py`, `WizardState` in `app/ui/state.py`). Ten
  questions (see `doc/ai/wizard-questions.md`) collect answers through
  buttons/number fields rather than typed text - each is phrased around the
  user's real-world situation (e.g. "Jezdíte i tam, kde bývá bláto, sníh
  nebo horší cesta?" instead of asking for a drivetrain) and mapped
  deterministically onto `StructuredRequirements`, so unlike the chat's
  `RequirementInterpreter` the wizard needs no AI call and works even
  without `ANTHROPIC_API_KEY` configured. `ConversationOrchestrator` gained
  `handle_wizard_answers`, sharing the same merge/recommend/explain pipeline
  as chat turns (`_apply_requirements`) so wizard- and chat-driven turns
  accumulate onto one conversation. `notes` is now shown in the
  requirements drawer (previously populated but never displayed).

## 0.2.12 — 2026-08-31

### Added
- Equipment surcharge prices are now captured and imported into the
  catalog. `skoda_equipment.py`'s parser already read the price column on
  Škoda's "Samostatné prvky výbavy" page but discarded it; the scraper's
  `EquipmentAssignment` gained `surcharge_amount`/`currency` columns to
  hold it, and `scripts/import_scraper_data.py` now imports
  STANDARD/OPTIONAL/NOT_AVAILABLE equipment rows into
  `option_items`/`option_availability` (PACKAGE rows, and OPTIONAL rows
  still missing a price, are skipped rather than fabricated - see that
  script's module docstring). Previously equipment/options were skipped
  entirely, since drivewise's `option_availability` CHECK constraint
  requires a price for every `optional` row and none was ever available.

## 0.2.11 — 2026-08-29

### Changed
- Catalog browsing now uses infinite scroll instead of a "Load more"
  button: scrolling the results column near its bottom fetches the next
  page automatically (`backend/app/ui/pages.py`'s `on_results_scroll`),
  with a small spinner shown while a page is in flight. The scroll
  container keeps using the browser's own `overflow-y-auto` scrollbar
  (not a virtualized list), so its thumb/track size stays accurate on its
  own as more cards are appended - no manual height bookkeeping needed.

## 0.2.10 — 2026-08-29

### Added
- BMW support in the scraper: discovery + parser for the brand's entire
  current lineup (29 model sections — combustion, electric, and plug-in
  hybrid — read generically from one combined price list rather than a
  hardcoded model list), with a PDF test fixture and parser tests
  (`scraper/monitors/discovery/bmw.py`, `scraper/parsers/bmw.py`).
- Wired BMW data into `scripts/import_scraper_data.py` so scraped results
  reach the catalog database.

### Fixed
- `scripts/import_scraper_data.py`'s `infer_drivetrain`/`infer_fuel_type`
  didn't recognize BMW's own AWD marker ("xDrive") or diesel suffix
  ("320d", fused onto the trim with no space, unlike other brands) —
  every BMW variant was defaulting to FWD/petrol regardless of its real
  drivetrain or fuel type.
- `powertrain_signature()` dedups "the same engine across trims" by
  stripping the trim label out of a variant's display name; for BMW the
  trim label already IS the row's entire distinguishing text (e.g.
  "320d"), so every row in a model collapsed onto one shared (and
  arbitrarily-classified) powertrain. `BmwParser` now folds
  displacement/power (and an explicit AWD marker for the few pairs that
  share an identical spec and differ only by xDrive) into the variant
  name so each row survives the stripping with its own distinct engine.

## 0.2.9 — 2026-08-29

### Added
- Mazda support in the scraper: discovery + parser for CX-5, 3 (hatchback
  and sedan), and CX-30, with PDF test fixtures and parser tests
  (`scraper/monitors/discovery/mazda.py`, `scraper/parsers/mazda.py`).
  Mazda's official price-list PDFs are an interactive-brochure export with
  duplicated/overlapping text layers, unlike any other brand's plain price
  tables — the parser's module docstring documents the extraction
  technique this needed (font-size filtering, off-page-content filtering,
  exact-position row grouping, and strict per-row column validation that
  silently drops a malformed row rather than risk extracting a wrong
  price).
- Wired Mazda data into `scripts/import_scraper_data.py` so scraped
  results reach the catalog database.

### Fixed
- The Mazda entry in `scraper/config/sources.yaml` listed model `3`
  unquoted, so YAML parsed it as the integer `3` instead of the string
  `"3"` — silently breaking the discoverer's model-matching for that one
  model (it compared against string captions and never matched an int).
  Caught by cross-checking the discoverer's live output against the
  configured model list before considering the source done.

## 0.2.8 — 2026-08-29

### Fixed
- The catalog-browsing header ("N vozů v katalogu") was built from
  `len(cars)` — the currently loaded page of results (capped at
  `page_size`, 20 by default) — rather than the real total, so it never
  read as more than the first page's size regardless of how many vehicles
  actually matched. Now uses `catalog_state.total`, the real count already
  returned by the backend on every page load (`backend/app/ui/pages.py`).

## 0.2.7 — 2026-08-29

### Added
- Mercedes-Benz support in the scraper: discovery + parser for C-Class and
  E-Class (sedan and estate body styles), reading the combined "Souhrnný
  ceník" PDF that covers the brand's entire lineup, with a PDF test fixture
  and parser tests (`scraper/monitors/discovery/mercedes_benz.py`,
  `scraper/parsers/mercedes_benz.py`).
- Wired Mercedes-Benz data into `scripts/import_scraper_data.py` so scraped
  results reach the catalog database.

### Fixed
- `scripts/import_scraper_data.py` assumed every scraper document covers
  exactly one model; Mercedes-Benz's combined price list broke that
  assumption (all its variants were being imported under a single model).
  Variants are now grouped by their own `model` value within a document,
  and `SourceDocument` rows are keyed by `(file_path, model)` instead of
  `file_path` alone, so one PDF can correctly back several models.

## 0.2.6 — 2026-08-29

### Added
- Hyundai support in the scraper: discovery + parser for i20, i30, Kona,
  Tucson (ICE and HEV/PHEV) and Santa Fe, with PDF test fixtures and parser
  tests (`scraper/monitors/discovery/hyundai.py`, `scraper/parsers/hyundai.py`).
- Wired Hyundai data into `scripts/import_scraper_data.py` so scraped results
  reach the catalog database.

## 0.2.5 — 2026-08-29

### Added
- `doc/carVendors.md` documenting the supported car vendors/brands.
- Catalog filter controls: a filter bar component in the NiceGUI UI, backing
  query parameters in the vehicles API, and matching state handling and tests.

## 0.2.4 — 2026-08-26

### Fixed
- Locale bug in `backend/app/ui/i18n.py`.

## 0.2.3 — 2026-08-26

### Added
- Pluggable LLM client abstraction (`backend/app/ai/llm.py`) with Groq as an
  additional provider alongside the existing one, plus config and tests.

## 0.2.2 — 2026-08-26

### Added
- Admin console page (`backend/app/ui/admin.py`) for backend administration,
  linked from the header.

(Merge of pull request #2, bringing in the NiceGUI migration branch.)

## 0.2.1 — 2026-08-25 / 2026-08-26

### Added
- `scripts/run.bat` to launch the unified backend+UI app.

### Fixed
- A rendering glitch in the NiceGUI pages module.

## 0.2.0 — 2026-08-25

### Changed — **Major: migration to NiceGUI, Node.js removed**
- Replaced the separate React/TypeScript/Vite frontend with a Python
  NiceGUI UI served directly by the FastAPI backend: chat column, header,
  requirements drawer, results grid, vehicle detail modal, sorting and i18n
  were all reimplemented under `backend/app/ui/`.
- Deleted the entire `frontend/` tree (React components, npm/Vite tooling,
  `package-lock.json`, TypeScript config) — the project is now a single
  Python stack end-to-end, run via `pyproject.toml` / `requirements.txt`.
- This is the dividing line between the `0.1.x` (polyglot: Node.js + Python)
  and `0.2.x` (pure Python) eras of the project.

---

## 0.1.24 — 2026-08-25

### Added
- `doc/db/natural_language_requests.md`: design proposal for translating
  free-text user requirements into structured technical car parameters.

## 0.1.23 — 2026-08-22

### Added
- `doc/db/drivewise-schema.png` database schema diagram.
- `doc/implemented_overview.md` summarizing the current state of the
  implementation, plus UI screenshots (`doc/gui/car_detail.jpg`,
  `doc/gui/main_screen.jpg`).

## 0.1.22 — 2026-08-16

### Added
- Sorting for the results grid: `SortControl` component, `useCustomOrder`
  hook, `sortCars` utility, and a backing `sort` query parameter on the
  vehicles API.

## 0.1.21 — 2026-08-16

### Added
- Vehicle detail modal shown on car-card click, with a dedicated API client
  (`vehicleDetail.ts`) and `useVehicleDetail` hook.

## 0.1.20 — 2026-08-15

### Changed
- Replaced frontend mock conversation data with real API clients
  (`api/catalog.ts`, `api/client.ts`, `api/conversation.ts`,
  `api/vehicleSummary.ts`) and matching hooks/stores, wiring the chat UI to
  live backend vehicle data for the first time.

## 0.1.19 — 2026-08-15

### Changed
- Strengthened the Claude Code skills to generate more consistent
  object-oriented code, and introduced a documentation rule requiring
  docstrings on all methods and parameters — applied across the backend
  (AI, services) and scraper (parsers, discovery, downloader) modules.

## 0.1.18 — 2026-08-15

### Added
- `scripts/import_scraper_data.py`: imports parsed scraper output into the
  backend catalog database.
- Alembic migration adding a "hybrid" fuel type.

## 0.1.17 — 2026-08-15

### Changed
- Moved `scraper.db` and downloaded price-list PDFs out of
  `scraper/storage/` into a shared top-level `storage/` directory used by
  both the scraper and the backend, with a new `storage/README.md`.

## 0.1.16 — 2026-08-15

### Changed
- Consolidated the separate `backend/requirements*.txt` and
  `scraper/requirements.txt` into unified root-level `requirements.txt` /
  `requirements-dev.txt`.

## 0.1.15 — 2026-08-15

### Added
- SQLite-backed catalog storage: a database seed script
  (`backend/app/db/seed.py`) and refined SQLAlchemy models/config.

## 0.1.14 — 2026-08-15

### Changed
- Switched the frontend's default locale from Czech to English; added an
  i18n config with separate `cs`/`en` translation files.

## 0.1.13 — 2026-08-15

### Changed
- Restructured project documentation: overhauled the root `README.md` and
  added `doc/README.md` as an index; trimmed and reorganized `roles.md` and
  updated the Claude skill docs and architecture/implementation-plan docs.

## 0.1.12 — 2026-08-14

### Added
- `doc/ai/claude-integration-brainstorm.md` exploring approaches for Claude
  API integration.
- Standalone scripts to run just the Vite frontend dev server
  (`scripts/run-ui.{bat,ps1,sh}`) plus a `.claude/launch.json` entry.

## 0.1.11 — 2026-08-13

### Added
- 8 additional OEM price lists registered in the scraper source config.
- Kia support: discovery + parser + test fixtures.
- Toyota support: discovery + parser + test fixtures.

## 0.1.10 — 2026-08-12 / 2026-08-13

### Added
- `doc/db/db-structure.md` notes and a detailed proposed database structure.
- `doc/po/MVP.md` and `doc/po/Version2.md` roadmap/scope documents.

## 0.1.9 — 2026-08-03

### Added
- Downloaded price-list PDFs and a local `scraper.db` snapshot committed
  into `scraper/storage/` for reproducible local development.
- Merged pull request #1 (`fb_webScraping` branch).

## 0.1.8 — 2026-07-20

### Added
- Backend AI layer: `requirement_interpreter.py` and
  `explanation_generator.py`.
- REST API endpoints for brands, conversations, models and vehicles.
- Service layer: `catalog.py`, `conversation.py`, `recommendation_engine.py`.
- Initial backend test suite (`tests/test_catalog_api.py`, `conftest.py`).

## 0.1.7 — 2026-07-20

### Added
- FastAPI backend scaffold: Alembic migrations, SQLAlchemy models for the
  catalog schema (brand, car model, trim, powertrain, configuration, color,
  option item/availability, price, source document) and `doc/api-contract.md`.

## 0.1.6 — 2026-07-20

### Added
- Claude Code skill definitions for the project's architecture, data model,
  scraper, and AI-recommendation domains (`.claude/skills/`).
- Sample OEM PDF price lists (Mazda CX-5, VW Tiguan) for scraper development.

## 0.1.5 — 2026-07-19

### Added
- Python web scraper service (`scraper/`): source discovery, PDF
  downloading, per-brand parsers, SQLite-backed models/repositories, and
  test fixtures/tests for Škoda and Volkswagen (ICE + EV) price lists.
- `scraper/README.md`.

## 0.1.4 — 2026-07-19

### Added
- `doc/main.md` and `doc/roles/roles.md` (team roles), followed by a
  formatting cleanup pass.

## 0.1.3 — 2026-07-18

### Added
- React + TypeScript + Vite frontend scaffold: chat column, results grid,
  car card, requirements drawer, app header components with mock
  conversation data, component tests, and tooling (`oxlint`, `tsconfig`).

## 0.1.2 — 2026-07-16

### Added
- `doc/prompt/CLAUDE.md` project rules for Claude Code.
- Graphical UI design proposals (HTML/PDF concept mockups) under `doc/gui/`.

## 0.1.1 — 2026-07-09

### Added
- `doc/arch/webScraping/Car_Price_List_Architecture.md` describing the
  web-scraping architecture.

### Changed
- Consolidated `arch/` and `prompt/` folders under `doc/`.

## 0.1.0 — 2026-07-01

### Added
- Initial commit (`.gitignore`, `README.md`).
- First three drafts of the system architecture (`arch/architecture.md`,
  `Car_Selector_Architecture.drawio`/`.jpg`).

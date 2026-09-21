# DriveWise AI — Implementation Overview

A car-selection assistant: users describe how they'll use a car in a chat, an AI layer turns that
into structured requirements, a deterministic engine filters/ranks the real catalog, and the AI
explains each result. A second, independent service scrapes manufacturer price lists to grow that
catalog. This doc is a snapshot of what's actually built, not the target architecture — see
`doc/arch/` and each service's own README for design docs and open items.

## Architecture

Two independent services, one shared SQLite dev database for backend + scraper (`storage/`):

- **`backend/`** — FastAPI: REST API, the recommendation engine, the AI conversation flow, and the
  chat UI (`app/ui/`, NiceGUI) — all one process, no separate frontend.
- **`scraper/`** — standalone pipeline that downloads OEM PDF price lists and extracts
  vehicles/prices/equipment into its own database. Not wired to the backend automatically; a script
  imports its data into the backend's catalog on demand.

## Tech stack

| Layer | Stack |
|---|---|
| Backend | Python, FastAPI, SQLAlchemy 2.x, Alembic, Pydantic v2, SQLite (dev) / PostgreSQL (target, dual-dialect schema) |
| AI | Anthropic Claude (default) or Groq, selected via `AI_PROVIDER` - both behind one `LlmClient` interface (`app/ai/llm.py`) |
| UI | NiceGUI (Python), mounted onto the same FastAPI app - no Node.js/npm anywhere in the repo |
| Scraper | Python, requests, BeautifulSoup, pdfplumber, SQLAlchemy, Click, PyYAML |

## Implemented features

**Catalog (backend + UI)**
- `GET /api/brands`, `GET /api/models/{id}`, `GET /api/vehicles` (paginated, sortable by
  price/alpha), `GET /api/vehicles/{configuration_id}` (full detail), `GET /api/vehicles/compare`.
- Schema: brand → model → {trims, powertrains, colors, option items, source documents} →
  configuration → {prices, configuration colors, option availability}. Business rules enforced at
  the DB level (unique "current" price per market, valid-date ordering, etc.) — see
  [`doc/db/implemented_overview` diagram](db/drivewise-schema.png) if present, or `doc/db/`.
- Currently seeded with one hand-verified vehicle (Mazda CX-5) plus real scraper-imported data
  (`scripts/import_scraper_data.py`).

**AI-driven conversation (backend `app/ai/`, `app/services/conversation.py`)**
- `POST /api/conversations` starts a chat; `POST /api/conversations/{id}/messages` sends a turn.
- Flow per turn: the LLM extracts `StructuredRequirements` from free text → a deterministic
  `RecommendationEngine` filters the catalog on hard constraints (body type, budget, fuel type) and
  scores the rest (drivetrain match, priority match, budget headroom) → the LLM generates a
  per-vehicle explanation. The AI never queries or ranks the database directly.
- Provider is Anthropic Claude by default, or Groq (`AI_PROVIDER=groq`) - see `app/ai/client.py`/
  `app/ai/llm.py` and `backend/README.md`'s Setup section.
- Conversation state is in-memory only (no persistence yet, no multi-process support).
- Degrades to a graceful "AI not configured" state if the selected provider's API key isn't set
  (still `ai_not_configured` as the underlying error code - see `app/services/conversation.py`);
  catalog browsing still works without it.

**UI (`backend/app/ui/`, NiceGUI)**
- Mounted directly onto the FastAPI app (`ui.run_with`, see `app/main.py`) - one process, calls the
  service layer in-process rather than over HTTP.
- Two-column chat layout: conversation on the left, results grid on the right.
- **Browsing mode** (default, before the AI has narrowed anything): paginated catalog with
  server-side sort (price asc/desc, alphabetical) or client-side drag-to-reorder ("custom").
- **Narrowed mode** (after the AI returns matches): shortlist with match scores/flags, sorted
  client-side.
- Requirements drawer showing the requirements extracted so far; vehicle detail modal; car cards.
- Admin console at `/admin` (`app/ui/admin.py`): run the scraper and the scraper → catalog import
  as subprocesses from the browser, with live streamed output. Admin-only (see login below).
- Passwordless email login (`app/services/auth.py`, `app/ui/auth.py`): a 6-digit code emailed to any
  address creates/opens a regular account; admin rights come from `ADMIN_EMAILS` / `users.is_admin`.
  Anonymous use of the catalog and chat stays open. Admin console and the AI-key dialog are
  admin-only.
- All user-facing copy is Czech (`app/ui/i18n.py`'s `STRINGS` dict) per project convention.
- pytest coverage in `backend/tests/ui/` - the state layer (`ConversationState`/`CatalogState`)
  against the real seeded database, plus the pure-function helpers (`sort_cars`, `format_money`,
  i18n pluralization). See `backend/README.md`'s Tests section for why this doesn't use NiceGUI's
  `User`-fixture DOM simulation.

**Scraper (`scraper/`)**
- Per-brand discoverer + parser plugins find and download PDF price lists
  (`scraper/config/sources.yaml` lists active sources), extract variants/prices/equipment, and
  normalize equipment names across brands.
- Stores into its own SQLite DB (`storage/scraper.db`), browsable via Datasette or any SQLite
  client; `scraper/verification/review_cli.py` cross-checks extracted data against the source PDF.
- Known gap: imported vehicles have no `option_items`/`option_availability` rows (no surcharge data
  in the source PDFs yet), so equipment lists are empty for scraper-imported cars.

## Running locally

**Backend + UI** (from repo root) — one process serves both:
```bash
python -m venv .venv
.venv\Scripts\activate            # Windows; source .venv/bin/activate elsewhere
pip install -r requirements-dev.txt
cd backend
alembic upgrade head               # creates storage/drivewise.db + schema
python -m app.db.seed              # seeds one hand-verified vehicle (safe to re-run)
python -m uvicorn app.main:app --reload   # http://localhost:8000/ is the UI, docs at /docs
```
Optional: `python scripts/import_scraper_data.py` (repo root) to load real scraped vehicles instead
of just the one seed vehicle. `ANTHROPIC_API_KEY` env var is required for the chat to do more than
degrade gracefully (catalog browsing works without it). Note: on some setups the bare `uvicorn`
command isn't on `PATH` — use `python -m uvicorn` as above.

**Scraper** (from repo root, same venv as backend):
```bash
python -m scraper.main
pytest scraper/tests/ -v
```

## Known gaps

- Conversation history/state isn't persisted (in-memory, single-process only).
- `min_seats` is accepted by the API but not actually filterable yet.
- Over-budget vehicles are hard-excluded; the "include with a warning flag" behavior isn't built.
- The AI layer hasn't been exercised against a live Claude API key — prompt behavior (JSON-only
  output, Czech free text) is unverified against the real model.
- Scraper-imported vehicles have no equipment (option) data.

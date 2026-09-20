# DriveWise AI – backend

FastAPI + SQLAlchemy + PostgreSQL (target) / SQLite (current default, see Database below). See
`doc/prompt/CLAUDE.md` for repo-wide conventions and `doc/api-contract.md` for the endpoint/schema
contract (source of truth for request/response shapes — keep it in sync with `app/schemas` when
either changes).

## Layout

```
app/
  db/        engine/session, declarative Base
  models/    SQLAlchemy models (the catalog: brands/models/trims/powertrains/configurations/...)
  schemas/   Pydantic request/response shapes, matching doc/api-contract.md
  services/  business logic - catalog queries, the deterministic recommendation engine,
             conversation orchestration
  ai/        the only place Claude API calls are allowed to happen (CLAUDE.md convention)
  api/       FastAPI routers
  ui/        the chat UI (NiceGUI, mounted onto this same app - see the UI section below)
  main.py    app instance, router wiring, error-shape exception handler, UI mounting
```

## Setup

Python dependencies are consolidated in one `requirements.txt`/`requirements-dev.txt` pair at the
**repo root** (shared with `scraper/` — see there for why), so the venv lives at the repo root too,
not here:

```bash
cd ..                          # repo root, if you're in backend/
python -m venv .venv
.venv/Scripts/activate         # Windows; `source .venv/bin/activate` elsewhere
pip install -r requirements-dev.txt   # requirements.txt + pytest/httpx for running tests
cd backend
```

Commands below (`uvicorn`, `alembic`, `pytest`) still need to run with `backend/` as the working
directory (that's where `app/`, `alembic.ini`, etc. live) — only dependency installation moved.

`DATABASE_URL` defaults to a SQLite file at `storage/drivewise.db` (repo root, see
`storage/README.md`) — no database server to install, see Database below. To use PostgreSQL
instead, set `DATABASE_URL` (or create a `.env` file):

```
DATABASE_URL=postgresql+psycopg://drivewise:drivewise@localhost:5432/drivewise
```

The AI layer supports two providers, chosen via `AI_PROVIDER` (default `anthropic`) - both are
called through the same `app/ai/llm.py` interface (`LlmClient.complete()`), so nothing outside
`app/ai/client.py` needs to know which one is active:

```
AI_PROVIDER=anthropic          # or "groq" - default is anthropic
ANTHROPIC_API_KEY=sk-ant-...
CLAUDE_MODEL=claude-sonnet-5   # optional, this is the default

# only needed if AI_PROVIDER=groq
GROQ_API_KEY=gsk_...
GROQ_MODEL=openai/gpt-oss-120b   # optional, this is the default
```

Groq (https://console.groq.com) has a free, no-credit-card developer tier - useful for dev/testing
without spending Anthropic credits, at the cost of a different (generally less instruction-precise)
model family; see the verification note below, which applies per-provider, not just to Claude.

Instead of putting a key in `.env`, you can enter it in the running app: the header's "AI klíč"
button opens a dialog whose value is kept in process memory only (never written to disk) and
overrides the environment's key. It has to be re-entered after every restart, and it is
process-wide - fine for a local single-user app, but not something to expose on a shared server.

There is no default for either provider's API key — `app/ai/client.py` raises loudly if the
*selected* provider's key is missing, rather than running the AI layer silently disabled. The
conversation flow degrades to a graceful "AI not configured" message without it (see the UI section
below - `ai_not_configured` is still the underlying error code, only now surfaced by the UI
directly rather than as an HTTP 503); the catalog data (brands/models/vehicles) don't need it at
all, regardless of provider.

The UI additionally uses:

```
NICEGUI_STORAGE_SECRET=...   # optional locally - see app/core/config.py; set a real value before
                              # any shared/public deployment
```

**The AI layer (`app/ai/requirement_interpreter.py`, `app/ai/explanation_generator.py`) was
written without access to a live API key and has not been exercised against either real provider.**
Verify prompt behavior before relying on it: does it reliably return JSON-only, is the
follow-up-question quality reasonable, and — both system prompts explicitly instruct this, but
it's an instruction, not a guarantee — does the model's free-text output (`follow_up_question`,
the per-vehicle explanation) actually come back in Czech, matching the rest of the UI (see
`doc/prompt/CLAUDE.md`'s language convention). Every *hardcoded* string in `app/services/
conversation.py` and the two AI modules already is Czech — that part went unverified for a while
since nothing rendered it live until a real UI was wired to this logic, not a scripted mock with
its own separately-authored Czech copy.

## Database

SQLite (a local file, `storage/drivewise.db`, gitignored) is the default for now, so the app runs
without installing anything database-related. The schema (`app/models/`, the Alembic migration) is
written to stay dual-dialect rather than SQLite-only — see `app/db/base.py`'s `BigIntPK` (SQLite
only auto-increments a PK when the column is literally `INTEGER`, unlike Postgres's `BIGSERIAL`)
and the `prices` table's partial unique index (`postgresql_where`/`sqlite_where` pair) — so
switching `DATABASE_URL` to Postgres later needs no model/migration changes.

```bash
alembic upgrade head      # creates storage/drivewise.db and the schema in it
python -m app.db.seed     # seeds two real, hand-verified vehicles (Mazda CX-5, VW Tiguan) - safe to
                           # re-run, skips if the DB already has data
```

`python -m app.db.seed` also calls `Base.metadata.create_all()` first, so on a totally fresh
checkout you can skip straight to it without running `alembic upgrade head` separately — Alembic
remains the source of truth for schema history either way (`alembic_version` gets stamped once you
do run it).

For real (not hand-seeded) catalog data, `python scripts/import_scraper_data.py` (repo root) loads
whatever `scraper/` has found in `storage/scraper.db` — see that script's docstring and
`storage/README.md` for what it does and doesn't carry over. Both can populate the same DB; run
either or both.

## Run (API + UI)

```bash
uvicorn app.main:app --reload
```

One process, one command: `http://localhost:8000/` serves the UI, interactive API docs are at
`http://localhost:8000/docs`, and `GET /api/brands` / `GET /api/vehicles` serve the REST API
directly (for any client other than the bundled UI). Try the API routes after seeding to see real
data.

## UI

The chat UI lives in `app/ui/` — [NiceGUI](https://nicegui.io) (Python), mounted directly onto this
same FastAPI app via `ui.run_with` (see the bottom of `app/main.py`). No Node.js/npm/separate
frontend process anywhere; the UI calls the service layer (`app/services/`) in-process instead of
over HTTP, using the same Pydantic response models the REST API returns (no separate wire-format
types to keep in sync, unlike a browser-based client would need).

```
app/ui/
  pages.py                  the whole app - one @ui.page("/"), wires everything together
  state.py                  per-connection state (ConversationState/CatalogState dataclasses) -
                             NiceGUI gives each browser connection its own call of pages.index(),
                             so plain local variables/closures are already private per connection;
                             no global store needed
  db.py                     per-action database sessions (see its docstring for why - `Depends`
                             only resolves once, at the initial page load, not on every later
                             click/message send)
  i18n.py                   Czech UI copy (the only language this app ships - see its docstring)
  money.py, sort.py         format_money() / sort_cars(), small pure helpers
  styles.py                 the design tokens (see doc/design-tokens.md), injected once via
                             ui.add_css - NiceGUI ships Tailwind support built in, so the same
                             utility classes work directly
  components/                one file per screen section (header, chat column, results grid,
                             requirements drawer, vehicle detail modal)
```

**Language:** Czech only, same as every other user-facing string in this codebase (see
`doc/prompt/CLAUDE.md`'s language convention) — all UI copy goes through `app/ui/i18n.py`'s `t()`/
`t_count()` against its `STRINGS` dict, not hardcoded strings in `components/`. Prices are always a
`Money` (`{amount, currency}`), formatted via `app/ui/money.py`'s `format_money()`.

**Browsing mode vs. narrowed mode:** the results area shows one of two things, decided by
`ConversationState.has_narrowed`:
- **Browsing** (default, and whenever the AI hasn't actually searched yet): the full catalog,
  loaded page by page via `CatalogState`/`app.services.catalog.list_vehicles` ("Načíst další" to
  fetch another page). Needs no conversation and no `ANTHROPIC_API_KEY` - it's what you see before
  typing anything, and what you're left with if the AI layer isn't configured.
- **Narrowed**: once a chat turn's response has `searched=True` (the recommendation engine actually
  ran), the AI-ranked/filtered shortlist from that turn. `has_narrowed` stays `True` through later
  follow-up-only turns (a real zero-match search must show "0 matches", not silently fall back to
  the catalog) - only restarting clears it.

**Sorting:** the dropdown offers recommended/price-ascending/price-descending/alphabetical/a
user-dragged "Moje pořadí" order. Price/alphabetical in browsing mode go to the backend and reset
to page 1 (sorting only the page(s) already loaded would be wrong); every option in narrowed mode,
and the custom order in either mode, sorts client-side via `app/ui/sort.py`'s `sort_cars()` against
whatever's already loaded. Drag-reordering uses NiceGUI's `make_sortable()` and persists across
reloads via `app.storage.user` (server-side, keyed by the browser's session cookie - the practical
equivalent of `localStorage` for a Python-only UI, see `state.py`/`pages.py`).

**Vehicle detail:** clicking a card (browsing or narrowed) opens a dialog with the full detail
(powertrain, colors, standard/optional equipment, price history) for that configuration, fetched on
open via `app/ui/state.py`'s `fetch_vehicle_detail`. Closes on backdrop click, Escape, or its close
button - all for free from NiceGUI's `ui.dialog` default (non-`persistent`) behavior.

**Admin console (`/admin`, `app/ui/admin.py`):** lets you trigger the scraper and the scraper →
catalog import from the browser - a "Spustit" (run) button per job, with the subprocess's live
output streamed into a scrollable log and a "Hotovo"/"Chyba" (done/error) status once it exits.
Also lists every configured OEM source (`config/sources.yaml`) with its active/inactive status.
Both jobs run as real subprocesses (`sys.executable -m scraper.main` /
`sys.executable scripts/import_scraper_data.py`), not in-process imports of `scraper`/`scripts`
code - keeps that boundary a real process boundary, so a scraper crash can't take the app down.
Running the scraper alone does **not** update the catalog the chat UI shows - run the import step
afterward for that (see the on-page description of each). No authentication (matches this app's
"no auth in v1" posture, see `doc/api-contract.md`) - fine locally, but don't expose this route on
a shared/public deployment as-is, since it lets a visitor trigger outbound network requests and DB
writes.

## Tests

```bash
pytest                    # everything: REST API tests + UI tests
pytest tests/ui           # just the UI layer
```

`tests/conftest.py` spins up a throwaway in-memory SQLite DB per test (via `Base.metadata.create_all`,
not Alembic), seeds it via `app.db.seed.seed_demo_data()` — the same real sample data drawn from
the Mazda CX-5 and VW Tiguan price lists in `storage/cars/` that `python -m app.db.seed` writes to
the persistent dev DB, one source of truth for both — and drives the FastAPI app through `TestClient` - so the
catalog endpoints (brands/models/vehicles/compare) are exercised end to end, not just imported. The
conversation endpoints are tested only up to the point that requires a live Claude API call (they
correctly degrade without a key); the AI layer itself isn't covered by this suite.

`seed_demo_data()` assigns every id explicitly rather than relying on autoincrement - not required
for correctness (see `BigIntPK` below, which makes autoincrement work on SQLite too), but it keeps
the seed deterministic and makes cross-referencing ids (e.g. `config_prime_2wd_id`) trivial in
tests.

`tests/ui/` covers the UI layer against that same seeded database (`tests/ui/conftest.py` patches
`app.ui.db.get_session` to yield it) - `test_state.py` exercises `ConversationState`/`CatalogState`
directly against real service calls (browsing-mode load, the `ai_not_configured` path, restart),
and `test_sort.py`/`test_money.py`/`test_i18n.py` cover the pure-function helpers. These are plain
async pytest tests, not NiceGUI's `User`-fixture DOM simulation: that fixture's current (NiceGUI
3.x) setup expects a `main_file` containing a literal `ui.run()` call, which doesn't fit this app's
`ui.run_with(app, ...)`-mounted-onto-an-existing-FastAPI-app structure - testing the state layer
directly covers the actual risk (real DB/orchestrator calls) independent of that mismatch. The
`nicegui.testing.user_plugin` pytest plugin is still registered (`pyproject.toml`) for whenever
that's worth revisiting.

## Migrations

```bash
alembic upgrade head          # apply all migrations
alembic upgrade head --sql    # preview the DDL without needing a live DB (offline mode)
alembic revision --autogenerate -m "message"   # generate a new migration from model changes
```

The first migration (`create catalog schema`) was authored by autogenerating against a throwaway
scratch SQLite DB and then hand-verified by rendering it as real Postgres DDL via
`alembic upgrade head --sql` — the emitted `op.create_table` calls use the actual model
Column/type objects, so they compile correctly for whichever dialect `DATABASE_URL` points at.
Since SQLite became the actual default (not just an authoring scratch DB), three spots needed
dialect-aware handling rather than being left Postgres-only, all verified with a real
`alembic upgrade head` → `downgrade base` → `upgrade head` round trip against SQLite directly (not
just `--sql` rendering):
- Every model's primary key uses `app/db/base.py`'s `BigIntPK` instead of bare `BigInteger` -
  SQLite only auto-increments a PK when the column type is exactly `INTEGER`, so a bare
  `BigInteger` PK (which is fine on Postgres/`BIGSERIAL`) silently never autoincrements on SQLite.
- The `prices` table's partial unique index needs both `postgresql_where` and `sqlite_where` - the
  Postgres dialect happens to accept a plain string for the former, but SQLite's DDL compiler
  requires an actual `text(...)` expression for the latter.
- Postgres native enum types (created implicitly, one per `Enum` column) aren't dropped by the
  generated `downgrade()`, which breaks a downgrade-then-upgrade round trip - fixed with a
  `DROP TYPE` loop, guarded to run only on `dialect.name == "postgresql"` since SQLite has no
  native enum type at all (`Enum` renders as plain `VARCHAR`, with no DB-level CHECK either -
  SQLAlchemy's `Enum` defaults to `create_constraint=False` - so validity is enforced by
  Pydantic/the ORM layer, not the DB, on SQLite) - see the bottom of
  `alembic/versions/6579b05df670_create_catalog_schema.py`. `alembic/versions/e49d32df7bd1_*.py`
  (adding the `hybrid` fuel type) is a second example of the same postgres/sqlite split, this time
  via `batch_alter_table` on the SQLite side (SQLite can't redefine a column's type in place).

## Known gaps (see doc/api-contract.md "open items" for the full list)

- Conversation state is in-memory only (`app/services/conversation.py`) - no persistence, no
  multi-process support. There are no `conversations`/`messages` tables in the DB schema yet.
- `min_seats` is accepted by `StructuredRequirements` and the `/api/vehicles` query params but
  isn't actually filterable - no source document states seat count.
- The recommendation engine's budget handling is a hard filter; the design concept's "include a
  slightly-over-budget car with a warning flag" behavior isn't implemented (`flag` is always null).
- `scripts/import_scraper_data.py` never populates `option_items`/`option_availability` (equipment)
  - the scraper's source data has no surcharge amount, which the schema requires for `optional`
    rows - so `standard_equipment`/`optional_equipment` are empty for every scraper-imported vehicle.

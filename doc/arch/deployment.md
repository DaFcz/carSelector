# Container / deployment architecture (proposal)

> **Status: proposal, not yet implemented.** No `Dockerfile` or `docker-compose.yml` exists in the
> repo yet — `.claude/skills/drivewise-architecture/SKILL.md` lists Docker as "aspirational — not
> yet set up". This doc lays out the intended shape so implementation can follow it directly. Once
> the files below exist and are current, move this doc's row in `doc/README.md` from "Proposals"
> to "Source of truth".

## Why one image, two roles

`backend/` (FastAPI + the NiceGUI UI mounted on it) and `scraper/` already share one
`requirements.txt`/`requirements-dev.txt` pair and one venv at the repo root (see
`storage/README.md` and both services' READMEs) — they stay independently deployable, but nothing
stops them sharing a base image. Build a single `python:3.12-slim` image and select behavior by
container command:

- **web role** — `uvicorn app.main:app`, run with `backend/` as the working directory.
- **scraper role** — `python -m scraper.main`, run from the repo root.

Split into two separate images only once the scraper actually adopts Playwright (see
`doc/arch/webScraping/Car_Price_List_Architecture.md`'s target stack) — a browser binary roughly
triples image size and has nothing to do with the web role.

## Compose services

| Service | Role | Notes |
|---|---|---|
| `web` | long-running | FastAPI + NiceGUI, **one replica only** (see Gotchas below) |
| `db` | long-running | Postgres 16, named volume for data |
| `migrate` | one-shot | `alembic upgrade head`; `web` depends on its completion |
| `scraper` | one-shot, profile-gated | batch run, not a service — trigger from host cron / scheduled task |
| `importer` | one-shot, profile-gated | `scripts/import_scraper_data.py`, same reasoning |

`scraper` and `importer` sit behind a Compose [profile](https://docs.docker.com/compose/profiles/)
so `docker compose up` doesn't start them by default — both are already manual/periodic steps per
the root `README.md` and `storage/README.md`, not part of the live request path.

**Volumes:**
- one named volume for Postgres's own data directory
- one bind/named volume mounted at the repo's `storage/` layout, for scraped PDFs
  (`storage/scraper/`) and NiceGUI's per-connection session files (`NICEGUI_STORAGE_PATH`, see
  `backend/app/core/config.py`)

## Repo-specific gotchas

- **NiceGUI holds per-connection state in-process and talks over WebSockets** (see
  `doc/prompt/CLAUDE.md`'s note on `app/ui/state.py` — one `pages.index()` call per browser
  connection, local closures as the per-connection store). This means: one `web` replica, or a
  platform/load balancer with session affinity. Do **not** put it behind plain round-robin
  load balancing.
- **`NICEGUI_STORAGE_SECRET`**: unset, a random one is generated into `storage/secret_key`
  (`app/core/config.py`) — set it explicitly in any deployed container (the file would be lost
  with the container, logging everyone out), and give the app a writable mount for the JSON
  session files it writes under `NICEGUI_STORAGE_PATH`. Set `PUBLIC_BASE_URL=https://...` (or
  `SESSION_COOKIE_HTTPS_ONLY=true`) so the session cookie is HTTPS-only.
- **Exclude `storage/` from the build context.** `storage/scraper/` alone is ~220 MB of PDFs
  (`storage/README.md`) and would otherwise bloat every image build; a `.dockerignore` is required
  before writing the `Dockerfile`.
- **No health endpoint exists today.** Add a trivial one (e.g. `GET /healthz` in `app/main.py` or
  a small router) so container healthchecks and any hosting platform's probes have something to
  hit — currently every route either goes through the versioned `/api/*` routers or the NiceGUI
  catch-all mount.
- **SQLite only survives in a container on a persistent volume.** `DATABASE_URL` defaults to the
  SQLite file at `storage/drivewise.db` (`backend/app/core/config.py`); on an ephemeral filesystem
  either switch to the `db` (Postgres) service via `DATABASE_URL`, or — since the catalog DB is
  currently small (352 KB) and read-mostly — bake a seeded copy into the image instead.

## Hosting: free or near-free options

| Option | Monthly cost | Main catch |
|---|---|---|
| Oracle Cloud Always Free ARM VM | $0 | Capacity often unavailable in a given region; card required at signup; you run the ops |
| Google Cloud Run | $0 for demo-level traffic | No disk, needs external Postgres, cold starts, session affinity required for NiceGUI |
| Render free tier | $0 | Sleeps when idle; free Postgres tier expires |
| Fly.io | ~$2–4 | No free tier anymore |
| Hetzner CX22 | ~$4 | Plain VPS, you run the ops |

**Recommendation:** if the goal is genuinely $0, the Oracle Always Free ARM instance is the best
fit — it's a full machine, so Compose, WebSockets, and volumes all work as designed, and the image
builds directly on the ARM box so architecture isn't a concern. If a couple of dollars a month is
acceptable to skip server maintenance, Fly.io with autostop suits this app's low-traffic profile
well.

Pricing and free-tier terms for all of the above change often — verify current terms before
committing to one.

## Next steps (not yet done)

1. `.dockerignore` (exclude `storage/`, `.venv/`, `__pycache__/`, etc.)
2. `Dockerfile` (single image, both roles selected by command)
3. `docker-compose.yml` (`web`, `db`, `migrate`, `scraper`/`importer` behind a profile, volumes as above)
4. A `GET /healthz` endpoint in `backend/app/main.py`
5. Real `NICEGUI_STORAGE_SECRET` handling for deployed environments (env var, not the code default)
6. Pick a hosting target from the table above and confirm current pricing

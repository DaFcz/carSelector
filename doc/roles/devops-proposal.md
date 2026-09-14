# DevOps Engineer — Proposal

Companion to [`devops_role.md`](devops_role.md) (the original 3-step outline). This expands it into
a concrete backlog grounded in the current state of the repo: no `Dockerfile`, no CI, no
`.github/` exist yet, but the container/hosting design is already written up as a proposal in
[`doc/arch/deployment.md`](../arch/deployment.md). Executing that proposal — plus the hardening and
CI/CD work it doesn't cover — is the DevOps engineer's job.

## Phase 1 — Containerize & deploy (devops_role.md's "First step")

1. **`.dockerignore`** — exclude `storage/` (the scraper's PDF corpus is ~220 MB and is committed
   to git on purpose, but must not bloat image builds), `.venv/`, `__pycache__/`.
2. **`Dockerfile`** — single `python:3.12-slim` image, role selected by container command (`web` =
   `uvicorn app.main:app` from `backend/`; `scraper` = `python -m scraper.main` from repo root).
   Already spec'd in the deployment doc.
3. **`docker-compose.yml`** — `web` (1 replica only, see Phase 2), `db` (Postgres 16), `migrate`
   (one-shot `alembic upgrade head`), and `scraper`/`importer` as profile-gated one-shot jobs, not
   always-on services.
4. **`GET /healthz`** — doesn't exist yet (`backend/app/main.py` only has `/api/*` routers + the
   NiceGUI catch-all mount at `/`). Needed for container healthchecks and any host's uptime probe.
5. **Real `NICEGUI_STORAGE_SECRET`** — `backend/app/core/config.py` currently defaults to
   `"dev-insecure-storage-secret"` if unset. Must be injected as a real secret in any deployed
   environment (not baked into the image).
6. **Switch `DATABASE_URL` to Postgres for prod** — SQLite (`storage/drivewise.db`) only survives
   on a persistent volume; on most free/ephemeral hosts it'll be wiped. The schema is already
   dual-dialect (SQLAlchemy models + Alembic migrations), so this is just an env var + a Postgres
   service.
7. **Pick a host** — the deployment doc already scored several free/near-free options (Oracle
   Always Free ARM, Fly.io, Render, Hetzner). The role doc names "endora" as the intended host —
   worth confirming whether that's still the plan, since it's not in the options table.

## Phase 2 — Hardening (devops_role.md's "Second step": HTTPS + monitoring)

8. **HTTPS/TLS** — via the hosting platform or a reverse proxy (Caddy/Traefik get you free Let's
   Encrypt certs with near-zero config).
9. **Session affinity / single replica** — NiceGUI holds per-connection UI state in-process over
   WebSockets (`backend/app/ui/state.py`). Don't put `web` behind round-robin load balancing;
   either pin to one instance or ensure the platform supports sticky sessions.
10. **Lock down `/admin`** — `backend/README.md` flags this explicitly: the admin console can
    trigger outbound scraper runs and DB writes with **no authentication**. Fine for local dev,
    unacceptable on a public deployment — needs at least basic auth or an IP allowlist before going
    live.
11. **Secrets management** — `ANTHROPIC_API_KEY`/`GROQ_API_KEY` currently live in a gitignored
    `backend/.env` locally; define how these get into the deployed environment (host secret store,
    not a committed file).
12. **Monitoring** — Grafana is named in the role doc; at minimum, container/host metrics + uptime
    alerting, plus basic app logs (nothing structured exists yet).
13. **Backups** — once on Postgres, a backup strategy for `db`'s volume didn't exist before
    (SQLite file was just gitignored and regenerable).

## Phase 3 — CI/CD (devops_role.md's "Third step", plus a gap not in the existing docs)

14. **GitHub Actions** — no `.github/workflows/` exists. Given the tests that already exist
    (`pytest` for backend + UI, `pytest scraper/tests/` against real PDF fixtures), a CI pipeline
    that runs both suites on PR is a natural first workflow, followed by an image-build-and-push
    step feeding the deploy target above.
15. **Server deployment from web administration** — devops_role.md's third step; once CI/CD exists,
    this is the natural next step (a deploy trigger reachable from an admin UI rather than a manual
    host login).
16. **Scraper scheduling** — the scraper/importer are explicitly manual/periodic steps (or
    triggerable via the admin console), not a live pipeline. If regular refreshes are wanted,
    that's a host-level cron or scheduled task, decided by DevOps rather than baked into the app.

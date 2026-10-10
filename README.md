# DriveWise AI (Car Selector)

AI-assisted car selection tool: chat about what you need, get vehicle recommendations filtered and
ranked against a catalog, with an AI-generated explanation for each pick. See
[`doc/main.md`](doc/main.md) for the original brief and [`doc/po/MVP.md`](doc/po/MVP.md) for what's
actually in scope right now.

## Status

The chat UI (NiceGUI, `backend/app/ui/` — one process with the backend, no separate frontend, no
Node.js) calls the service layer directly and shows real catalog data (real brands/models/trims/
prices) once populated:

- The backend's catalog can be populated two ways: hand-seeded demo data (`python -m app.db.seed`,
  a couple of real price lists in `storage/cars/`) or a real import of everything the scraper has
  found (`python scripts/import_scraper_data.py`) — see that script's docstring for exactly what it
  does and doesn't carry over (e.g. equipment/options aren't imported yet, no surcharge data to
  import). This import is a manual/periodic step, not a live pipeline — re-run it after every scrape.
- The chat itself (understanding what you typed, ranking, explanations) needs `ANTHROPIC_API_KEY`
  set on the backend — without it, starting a conversation and seeing the intro message still
  works, but sending a message returns a graceful "AI not configured" response instead of results
  (shown as a banner in the UI, not a crash).
- The scraper populates its own database independently — see `storage/README.md` for how the two
  connect (or don't, without running the import).

See each subproject's README for specifics, and `doc/api-contract.md` "open items" for known gaps.

## Repository structure

```
backend/    FastAPI + SQLAlchemy + SQLite (dev default) / PostgreSQL (target) — REST API,
            recommendation engine, Claude integration, and the UI (app/ui/, NiceGUI) — one process
scraper/    Standalone Python service — downloads & parses manufacturer PDF price lists
doc/        Architecture, API contract, DB schema, scope decisions — see doc/README.md for the index
scripts/    Cross-cutting glue — import_scraper_data.py (scraper.db → drivewise.db)
storage/    All local DB files + PDF copies for backend/ and scraper/ — see storage/README.md
.claude/    Claude Code project config: skills (doc/prompt/CLAUDE.md is the main conventions file)
requirements.txt, requirements-dev.txt   Python deps for backend/ (including its UI) + scraper/ —
            one shared venv, no Node.js/npm anywhere in this repo
```

## Quickstart

The UI is served by the backend process itself - starting the backend starts the UI too, there's
no separate frontend step.

1. Python setup (once, for backend/ and scraper/):
   ```bash
   python -m venv .venv
   .venv/Scripts/activate    # Windows; `source .venv/bin/activate` elsewhere
   pip install -r requirements-dev.txt
   pre-commit install        # Ruff lint/format on every commit, see "Lint & format" below
   ```
2. Backend + UI — see [`backend/README.md`](backend/README.md) (SQLite by default, no server to
   install; needs `ANTHROPIC_API_KEY` for the AI layer to do more than degrade gracefully)
3. Load real catalog data: `python scripts/import_scraper_data.py` (or `python -m app.db.seed`
   from `backend/` for just the small hand-verified demo dataset)
4. Scraper (optional, populates its own DB independently) — see [`scraper/README.md`](scraper/README.md)

## Lint & format

[Ruff](https://docs.astral.sh/ruff/) lints and formats all Python in the repo (backend/, scraper/,
scripts/) from one config in the root `pyproject.toml`. Run from the repo root:

```bash
ruff check --fix .
ruff format .
```

`ruff check .` and `ruff format --check .` must both pass before a change is done. To have git
run both on staged files automatically, install the pre-commit hook once per clone
(`.pre-commit-config.yaml`; a commit Ruff had to fix is stopped - re-`git add` and commit again):

```bash
pre-commit install
```

The bulk
reformat commit is listed in `.git-blame-ignore-revs`; to have `git blame` skip it, run once:
`git config blame.ignoreRevsFile .git-blame-ignore-revs`.

## Documentation

Start at [`doc/README.md`](doc/README.md) for an index of what's a current source of truth versus
historical/brainstorm material.

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# SQLite file under the repo-root storage/ directory is the default for now
# - no local Postgres install required to run the app. Lives alongside
# scraper/'s scraper.db and PDF downloads (storage/scraper/) rather than
# inside backend/, so all local data files sit in one place - see
# storage/README.md. The schema (app/models/, alembic/) targets Postgres as
# the eventual production database and is kept dual-dialect-compatible (see
# app/db/base.py's BigIntPK, and the sqlite_where/postgresql_where pair on
# the prices partial index) rather than SQLite-only; switch back by setting
# DATABASE_URL, e.g.:
#   postgresql+psycopg://drivewise:drivewise@localhost:5432/drivewise
_DEFAULT_SQLITE_PATH = Path(__file__).resolve().parents[3] / "storage" / "drivewise.db"
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{_DEFAULT_SQLITE_PATH}")

# Which LLM provider app/ai/client.py builds - "anthropic" (default) or
# "groq". Both are exposed behind the same LlmClient.complete() interface
# (app/ai/llm.py), so nothing outside app/ai/client.py needs to know which
# one is active. Only the selected provider's API key is required - see
# app/ai/client.py for the "fail loudly, but only if actually selected"
# behavior.
AI_PROVIDER = os.getenv("AI_PROVIDER", "anthropic").strip().lower()

# No default - the AI layer must fail loudly (see app/ai/client.py) rather
# than silently run without a key.
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-5")

# Groq (https://console.groq.com) - an alternative provider with a free,
# no-credit-card developer tier (rate-limited, not credit-limited), useful
# for dev/testing without spending Anthropic credits. Groq retires models
# on a schedule (https://console.groq.com/docs/deprecations): the former
# default llama-3.3-70b-versatile was shut down on 2026-08-16, after which
# calls fail with "model not available". openai/gpt-oss-120b is the
# replacement Groq names for it - a reasoning model, which
# app/ai/llm.py's GroqLlmClient accounts for. Prompt behavior against it is
# unverified (same caveat backend/README.md already documents for Claude).
# If this one is retired too, override with GROQ_MODEL in the environment.
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")

# Origins an external client (not the bundled UI, which is served from this
# same origin - see app/ui/ - and never needs CORS) can call this API from.
# Kept, unchanged, for anything that hits /api/* directly (tooling, a
# future separate client). The localhost:5173 default predates the bundled
# UI (it was Vite's dev server origin); left as-is since changing a public
# API's CORS default isn't part of a frontend-only migration.
CORS_ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.getenv(
        "CORS_ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
    ).split(",")
    if origin.strip()
]

# Signs NiceGUI's session cookie and is required for app.storage.user (used
# to persist the "custom sort order" drag result across reloads - see
# app/ui/state.py). The fallback is fine for local dev (nothing sensitive
# is stored - just a drag order); set a real secret before any shared/public
# deployment.
NICEGUI_STORAGE_SECRET = os.getenv("NICEGUI_STORAGE_SECRET", "dev-insecure-storage-secret")

# Where app.storage.user writes its per-browser JSON files - kept under
# storage/ with the rest of this project's local data files (see
# storage/README.md) rather than NiceGUI's own default (.nicegui/ next to
# the working directory). NiceGUI reads this from the environment itself
# (not a ui.run_with(...) argument), and must see it before its storage
# module first initializes - setdefault here so it's set as early as
# possible (this module loads before app.ui.pages ever imports nicegui)
# without overriding an operator-supplied value.
NICEGUI_STORAGE_PATH = os.environ.setdefault(
    "NICEGUI_STORAGE_PATH", str(Path(__file__).resolve().parents[3] / "storage" / "nicegui")
)

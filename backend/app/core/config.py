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

# --- Login (passwordless, 6-digit code by email - see app/services/auth.py) ---

# Key for the HMAC that hashes login codes before they're stored. A 6-digit
# code is only 10^6 possibilities, so a plain hash would be reversible
# instantly if the table leaked; keying it makes a leaked table useless
# without this secret. Falls back to the NiceGUI session secret so a
# deployment only has to configure one secret.
AUTH_SECRET = os.getenv("AUTH_SECRET") or NICEGUI_STORAGE_SECRET

# Emails that become admins the moment they log in (comma-separated,
# case-insensitive). Grant-only bootstrap: removing an address here does not
# demote anyone - `users.is_admin` is the source of truth after that.
ADMIN_EMAILS = frozenset(
    email.strip().lower() for email in os.getenv("ADMIN_EMAILS", "").split(",") if email.strip()
)

LOGIN_CODE_TTL_MINUTES = int(os.getenv("LOGIN_CODE_TTL_MINUTES", "10"))
LOGIN_CODE_MAX_ATTEMPTS = int(os.getenv("LOGIN_CODE_MAX_ATTEMPTS", "5"))
# Code requests per rolling hour, per email address and per client IP.
LOGIN_CODE_MAX_REQUESTS_PER_EMAIL_HOUR = int(os.getenv("LOGIN_CODE_MAX_REQUESTS_PER_EMAIL_HOUR", "5"))
LOGIN_CODE_MAX_REQUESTS_PER_IP_HOUR = int(os.getenv("LOGIN_CODE_MAX_REQUESTS_PER_IP_HOUR", "20"))
# How long a login stays valid; enforced server-side against the timestamp
# stored in the session (app/ui/auth.py), independent of the cookie's own
# lifetime.
AUTH_SESSION_DAYS = int(os.getenv("AUTH_SESSION_DAYS", "30"))

# How login codes reach the user: "console" (default - prints the code to
# the server log, for local development only) or "smtp". Defaults to the
# safe-for-dev option rather than failing, so the app still starts with no
# mail server configured; app/services/mailer.py logs a loud warning when
# "console" is active.
EMAIL_BACKEND = os.getenv("EMAIL_BACKEND", "console").strip().lower()
SMTP_HOST = os.getenv("SMTP_HOST")
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
# Envelope/header sender; defaults to SMTP_USER since most providers only
# accept their own account address.
SMTP_FROM = os.getenv("SMTP_FROM") or SMTP_USER
# Display name shown next to the sender address in the recipient's inbox.
SMTP_FROM_NAME = os.getenv("SMTP_FROM_NAME", "Rovis")
# "starttls" (default), "ssl" (implicit TLS) or "none" (unencrypted - only for
# a trusted local relay; the password would travel in clear text).
SMTP_SECURITY = os.getenv("SMTP_SECURITY", "starttls").strip().lower()
# Defaults to the conventional port for the chosen security mode (587 / 465 /
# 25); a blank SMTP_PORT= line counts as unset.
SMTP_PORT = int(os.getenv("SMTP_PORT") or {"starttls": 587, "ssl": 465, "none": 25}.get(SMTP_SECURITY, 587))

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

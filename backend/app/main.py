from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import brands, conversations, models, vehicles
from app.core.config import CORS_ALLOWED_ORIGINS

app = FastAPI(title="DriveWise AI API")

# The frontend (Vite dev server, a different origin/port) calls this API
# directly from the browser - no auth/cookies in v1 (see doc/api-contract.md),
# so a small fixed allowlist is enough; no credentials are sent.
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ALLOWED_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """doc/api-contract.md's error shape is `{"error": {...}}` at the top
    level - FastAPI's default wraps HTTPException.detail under `"detail"`
    instead, so unwrap it here. `app.api.errors.api_error` always sets
    `detail` to the contract shape already; anything else (FastAPI's own
    validation errors, etc.) gets wrapped generically.
    """
    if isinstance(exc.detail, dict) and "error" in exc.detail:
        return JSONResponse(status_code=exc.status_code, content=exc.detail)
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": "http_error", "message": str(exc.detail), "details": {}}},
    )


app.include_router(brands.router, prefix="/api")
app.include_router(models.router, prefix="/api")
app.include_router(vehicles.router, prefix="/api")
app.include_router(conversations.router, prefix="/api")

# The UI (see app/ui/) is mounted last and at "/" on purpose: ui.run_with
# mounts NiceGUI's own sub-app as a catch-all at mount_path, so mounting it
# before the /api/* routers above would swallow every request meant for
# them. The import (not just the ui.run_with call) is required: @ui.page
# only registers a route as a side effect of the decorator running, and
# nothing above this line has imported app.ui.pages yet. Imported via
# `from ... import` (not `import app.ui.pages`) deliberately - the latter
# would bind the name `app` in this module's namespace to the top-level
# `app` package, clobbering the `app = FastAPI(...)` instance above.
from nicegui import ui  # noqa: E402

from app.core.config import NICEGUI_STORAGE_SECRET  # noqa: E402
from app.ui import pages as _ui_pages  # noqa: E402, F401
from app.ui.admin import register_admin_page  # noqa: E402

from app.services.mailer import log_email_backend_status  # noqa: E402

register_admin_page()
# Say at startup how login codes will be delivered (see there) - a forgotten
# EMAIL_BACKEND=smtp should be visible now, not when someone waits for a mail.
log_email_backend_status()
ui.run_with(app, mount_path="/", storage_secret=NICEGUI_STORAGE_SECRET, title="Rovis")

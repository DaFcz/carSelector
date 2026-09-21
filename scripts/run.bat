@echo off
REM Starts the DriveWise AI app: one process serves both the REST API
REM (/api/*) and the chat UI (/) - see backend/app/ui/ and
REM backend/README.md's "Run (API + UI)" section. There's no separate
REM frontend to start since the Node.js/React frontend was replaced by a
REM NiceGUI UI mounted directly onto this same FastAPI app.

setlocal
cd /d "%~dp0.."

if exist ".venv\Scripts\activate.bat" (
    call ".venv\Scripts\activate.bat"
) else (
    echo No .venv found at repo root - run this first:
    echo   python -m venv .venv
    echo   .venv\Scripts\activate
    echo   pip install -r requirements-dev.txt
    exit /b 1
)

REM Applies pending schema migrations (e.g. the users/login_codes tables
REM added with email login) - a no-op when already up to date. Like the
REM import below, a failure doesn't block starting the app.
echo Applying database migrations...
pushd backend
python -m alembic upgrade head
popd

REM Pulls in whatever scraper/ has found since the catalog was last
REM imported (storage/scraper.db -> storage/drivewise.db) - safe to
REM re-run every time (natural-key lookups, append-only price history,
REM see scripts/import_scraper_data.py's own docstring). Failure here
REM (e.g. no storage/drivewise.db yet - run alembic upgrade head first)
REM doesn't block starting the app, just leaves the catalog as it was.
echo Importing scraper data into the catalog...
python scripts\import_scraper_data.py

cd backend
echo Starting DriveWise AI at http://localhost:8000/  (API docs at /docs)
python -m uvicorn app.main:app --reload

endlocal

"""Admin console (`/admin`): lets a developer trigger the scraper and the
scraper -> catalog import from the browser instead of a terminal, with
live streamed output.

Deliberately subprocess-based - `python -m scraper.main` and
`python scripts/import_scraper_data.py` via `sys.executable` - rather than
importing `scraper`/`scripts` code in-process. This keeps the existing
UI/backend <-> scraper boundary (see `doc/prompt/CLAUDE.md`) a real
process boundary, not just a code-organization one: a scraper crash can
never take down this app, and there's no sys.path/import-order coupling
between three otherwise-independent codebases to get wrong. The one
exception is `scraper.sources.registry.SourceRegistry`, read directly
in-process below - it only parses a YAML file (no DB/network), so there's
no boundary risk worth a subprocess for a read-only listing.

Admin-only: the page checks `AuthState.is_admin` (see `app/ui/auth.py`)
before building anything, and builds nothing but a login prompt / "no
rights" message otherwise. That matters more than hiding a link - the job
buttons' handlers only exist on the pages of users who passed the check, so
there is nothing for a non-admin's browser to send events to. The console
lets whoever reaches it trigger outbound network requests and write to the
DB, hence the wall.
"""

import asyncio
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from nicegui import ui

from app.ui.auth import AuthState
from app.ui.components.login_dialog import login_dialog
from app.ui.i18n import t
from app.ui.styles import register_styles

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRAPER_DB_PATH = REPO_ROOT / "storage" / "scraper.db"

# scraper/ lives at the repo root, not under backend/, so it isn't on
# sys.path when this app runs as `uvicorn app.main:app` from backend/ -
# same fix scripts/import_scraper_data.py applies for its own imports.
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scraper.sources.registry import Source, SourceRegistry  # noqa: E402

SCRAPER_COMMAND = [sys.executable, "-m", "scraper.main"]
IMPORT_COMMAND = [sys.executable, str(REPO_ROOT / "scripts" / "import_scraper_data.py")]


@dataclass
class JobState:
    """Tracks one long-running background job (one subprocess run) - its
    live output and whether it's currently running.
    """

    is_running: bool = False
    lines: list[str] = field(default_factory=list)
    return_code: int | None = None

    async def run(self, command: list[str], on_output: Callable[[], None]) -> None:
        """Runs `command` as a subprocess, streaming its combined
        stdout/stderr into `self.lines` line by line as it produces them.
        No-ops if this job is already running.

        Args:
            command: Argv to run, e.g. `SCRAPER_COMMAND`.
            on_output: Called after every state change (start, each new
                line, completion) so the caller can re-render.
        """
        if self.is_running:
            return
        self.is_running = True
        self.lines = []
        self.return_code = None
        on_output()

        process = await asyncio.create_subprocess_exec(
            *command,
            cwd=str(REPO_ROOT),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        assert process.stdout is not None
        async for raw_line in process.stdout:
            self.lines.append(raw_line.decode("utf-8", errors="replace").rstrip())
            on_output()

        self.return_code = await process.wait()
        self.is_running = False
        on_output()


def _sources_table() -> None:
    """Lists every configured OEM source (active or not) - brand, parser,
    model coverage - read straight from `config/sources.yaml`.
    """
    sources = SourceRegistry().load_all()
    with ui.column().classes("w-full gap-2"):
        ui.label("Zdroje (config/sources.yaml)").classes("text-[13px] font-bold uppercase tracking-wide text-subtext")
        with ui.column().classes("w-full gap-1.5"):
            for source in sources:
                _source_row(source)


def _source_row(source: Source) -> None:
    """One line in the sources list.

    Args:
        source: The source to render.
    """
    status_classes = (
        "rounded-full px-2.5 py-1 text-[11px] font-semibold "
        + ("bg-accent-soft text-accent" if source.active else "bg-panel-2 text-subtext")
    )
    with ui.row().classes("w-full items-center gap-3 rounded-control border border-border bg-panel px-3.5 py-2.5"):
        ui.label("aktivní" if source.active else "neaktivní").classes(status_classes)
        with ui.column().classes("gap-0"):
            ui.label(f"{source.brand} ({source.parser_key})").classes("text-[13px] font-semibold text-text")
            ui.label(", ".join(source.models) or "—").classes("text-[11.5px] text-subtext")


def _job_section(title: str, description: str, state: JobState, command: list[str]) -> None:
    """Builds one job's UI: a button, status, and a scrollable, live
    output log.

    Args:
        title: Heading shown above the button.
        description: One-line explanation of what running this does.
        state: The job's `JobState` - fresh per page load (see `admin`).
        command: Argv to run when the button is clicked.
    """
    with ui.column().classes(
        "w-full gap-2.5 rounded-card border border-border bg-panel p-4 shadow-card"
    ):
        ui.label(title).classes("text-[15px] font-bold text-text")
        ui.label(description).classes("text-[12.5px] text-subtext")

        @ui.refreshable
        def content() -> None:
            with ui.row().classes("items-center gap-2.5"):
                button = ui.button(
                    "Běží…" if state.is_running else "Spustit",
                    on_click=lambda: state.run(command, content.refresh),
                ).props("no-caps unelevated").classes(
                    "rounded-control bg-accent px-4 py-2 text-[13px] font-semibold text-accent-text"
                )
                button.set_enabled(not state.is_running)
                if state.return_code is not None:
                    ok = state.return_code == 0
                    ui.label("Hotovo" if ok else f"Chyba (kód {state.return_code})").classes(
                        "text-[12.5px] font-semibold " + ("text-accent" if ok else "text-flag")
                    )

            if state.lines:
                with ui.scroll_area().classes(
                    "h-[240px] w-full rounded-control border border-border bg-panel-2 p-2.5"
                ) as log_area:
                    ui.label("\n".join(state.lines)).classes(
                        "whitespace-pre-wrap font-mono text-[11.5px] text-text"
                    )
                log_area.scroll_to(percent=1.0)

        content()


def _access_denied(auth_state: AuthState) -> None:
    """Builds the page non-admins get instead of the console: a login
    prompt if anonymous, a "no admin rights" note if logged in. Logging in
    from here reloads the page, which then shows the console if the account
    turned out to be an admin.

    Args:
        auth_state: This connection's login state.
    """
    # The client is captured now, not looked up when the reload runs: by then
    # the click handler that triggers it belongs to a dialog button that the
    # dialog's own re-render has already deleted, and `ui.navigate.reload()`
    # called from that dead slot raises "parent element ... has been deleted".
    client = ui.context.client

    def reload_page() -> None:
        with client:
            ui.navigate.reload()

    open_login_dialog = login_dialog(auth_state, reload_page)

    with ui.column().classes("min-h-screen w-full items-start bg-bg text-text gap-4 p-8"):
        ui.label("Rovis — Admin").classes("text-xl font-bold text-text")
        if auth_state.user is None:
            ui.label(t("auth.adminOnly")).classes("text-[13px] text-subtext")
            ui.button(t("header.login"), icon="login", on_click=open_login_dialog).props("no-caps unelevated").classes(
                "rounded-control bg-accent px-3.5 py-2 text-[13px] font-semibold text-accent-text"
            )
        else:
            ui.label(t("auth.adminOnly")).classes("text-[13px] text-subtext")
            ui.label(t("auth.adminOnlyLoggedIn", email=auth_state.user.email)).classes("text-[13px] text-subtext")
        ui.link(t("auth.backToApp"), "/").classes("text-[13px] text-accent")


def register_admin_page() -> None:
    """Registers `@ui.page("/admin")` as a side effect - imported once
    from `app/main.py`, same pattern as `app/ui/pages.py`.
    """

    @ui.page("/admin")
    async def admin() -> None:
        register_styles()
        auth_state = AuthState()
        await auth_state.refresh()
        if not auth_state.is_admin:
            _access_denied(auth_state)
            return

        scraper_state = JobState()
        import_state = JobState()

        with ui.column().classes("min-h-screen w-full bg-bg text-text gap-6 p-8"):
            with ui.row().classes("w-full items-center justify-between"):
                ui.label("Rovis — Admin").classes("text-xl font-bold text-text")
                ui.link("← Zpět na appku", "/").classes("text-[13px] text-accent")

            with ui.column().classes("w-full max-w-[720px] gap-6"):
                _sources_table()

                _job_section(
                    "1. Spustit scraper",
                    "Stáhne a zpracuje nové ceníky ze všech aktivních zdrojů do storage/scraper.db. "
                    "Samo o sobě nemění katalog, který appka zobrazuje - k tomu slouží krok níže.",
                    scraper_state,
                    SCRAPER_COMMAND,
                )
                _job_section(
                    "2. Naimportovat do katalogu",
                    "Přenese nově zparsovaná data ze storage/scraper.db do katalogu (storage/drivewise.db) "
                    "- teprve po tomto kroku se nové/aktualizované vozy objeví v appce. Bezpečné spouštět "
                    "opakovaně.",
                    import_state,
                    IMPORT_COMMAND,
                )

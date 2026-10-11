"""Admin console (`/admin`), six tabs:

- "Data": the configured OEM sources (`config/sources.yaml`) - read-only.
- "Ovládání" (Controls): lets a developer trigger the scraper and the
  scraper -> catalog import from the browser instead of a terminal, with
  live streamed output.
- "AI komunikace": the full trace of LLM (Groq / Anthropic) requests and
  responses - see `app/ui/components/llm_trace_panel.py`.
- "Autoři": author-role requests and current authors - see
  `app/ui/components/authors_admin_panel.py`.
- "Zpětná vazba": user feedback - see
  `app/ui/components/feedback_admin_panel.py`.
- "Porovnání": the most compared car models and what they're compared
  with - see `app/ui/components/comparison_stats_admin_panel.py`.

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
DB, hence the wall. Because an open page outlives that check, the job
buttons and the AI trace's refreshes re-check admin rights against the
database when they act (`still_admin` in `admin`): an admin demoted or
deactivated meanwhile gets the page reloaded into the "no rights" view
instead.
"""

import asyncio
import json
import logging
import os
import subprocess
import sys
import threading
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path

from nicegui import app, ui
from nicegui.events import ValueChangeEventArguments

from app.ui import feedback_state
from app.ui.auth import AuthState
from app.ui.components.authors_admin_panel import authors_admin_panel
from app.ui.components.comparison_stats_admin_panel import comparison_stats_admin_panel
from app.ui.components.feedback_admin_panel import feedback_admin_panel
from app.ui.components.llm_trace_panel import llm_trace_panel
from app.ui.components.login_dialog import login_dialog
from app.ui.i18n import t
from app.ui.styles import register_styles

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRAPER_DB_PATH = REPO_ROOT / "storage" / "scraper.db"

# scraper/ lives at the repo root, not under backend/, so it isn't on
# sys.path when this app runs as `uvicorn app.main:app` from backend/ -
# same fix scripts/import_scraper_data.py applies for its own imports.
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scraper.sources.registry import Source, SourceRegistry  # noqa: E402

# `-u`: unbuffered output. Python block-buffers stdout when it's a pipe
# rather than a terminal, so without it the live log (and the progress bar)
# only got output in ~8 KB bursts, often not until the job ended.
SCRAPER_COMMAND = [sys.executable, "-u", "-m", "scraper.main"]
IMPORT_COMMAND = [sys.executable, "-u", str(REPO_ROOT / "scripts" / "import_scraper_data.py")]

# Lines in this format are progress updates, not log output - see
# `scraper/progress.py` for the format (the import script prints the same).
PROGRESS_PREFIX = "PROGRESS "

# `app.storage.general` key: {job key: seconds the last successful run took}
# - the basis of the time-left estimate before (and blended with) progress.
LAST_DURATIONS_KEY = "admin_job_last_durations"


@dataclass
class JobProgress:
    """The latest `PROGRESS` line of a running job.

    `step` (1-based) of `steps` is the outer unit (a source, a document),
    `sub` of `subs` the optional progress inside it.
    """

    step: int
    steps: int
    item: str
    sub: int | None = None
    subs: int | None = None

    @property
    def fraction(self) -> float:
        """How much of the job is done, 0.0-1.0: whole finished steps plus
        the finished share of the current one."""
        if self.steps <= 0:
            return 0.0
        inner = self.sub / self.subs if self.sub is not None and self.subs else 0.0
        return min(max((self.step - 1 + inner) / self.steps, 0.0), 1.0)


def parse_progress(line: str) -> JobProgress | None:
    """Args:
        line: One line of job output.

    Returns:
        The progress it reports, or `None` if it isn't a (well-formed)
        progress line - malformed ones are treated as ordinary output.
    """
    if not line.startswith(PROGRESS_PREFIX):
        return None
    try:
        payload = json.loads(line[len(PROGRESS_PREFIX) :])
        return JobProgress(
            step=int(payload["step"]),
            steps=int(payload["steps"]),
            item=str(payload.get("item", "")),
            sub=int(payload["sub"]) if payload.get("sub") is not None else None,
            subs=int(payload["subs"]) if payload.get("subs") is not None else None,
        )
    except (ValueError, KeyError, TypeError):
        return None


def estimate_remaining(elapsed: float, fraction: float, last_duration: float | None) -> float | None:
    """Estimates the seconds left in a running job from two sources:

    - history: the last successful run's duration minus the time elapsed
      (useless once this run has already taken longer than that one);
    - progress: elapsed time extrapolated over the remaining fraction
      (too noisy in the first few percent to be shown on its own).

    When both are available they're blended, trusting progress more the
    further the run gets.

    Args:
        elapsed: Seconds since the job started.
        fraction: `JobProgress.fraction` (0 if no progress yet).
        last_duration: Seconds the last successful run took, if known.

    Returns:
        Seconds left, or `None` if there's nothing to base a guess on.
    """
    by_history = last_duration - elapsed if last_duration and elapsed < last_duration else None
    by_progress = elapsed * (1 - fraction) / fraction if fraction >= 0.05 else None
    if by_history is not None and by_progress is not None:
        return fraction * by_progress + (1 - fraction) * by_history
    return by_progress if by_progress is not None else by_history


def format_duration(seconds: float) -> str:
    """Args:
        seconds: A duration.

    Returns:
        `"m:ss"`, e.g. `"4:07"`.
    """
    total = max(int(round(seconds)), 0)
    return f"{total // 60}:{total % 60:02d}"


@dataclass
class JobState:
    """Tracks one long-running background job (one subprocess run) - its
    live output, latest progress, timing, and whether it's currently running.
    """

    is_running: bool = False
    lines: list[str] = field(default_factory=list)
    return_code: int | None = None
    progress: JobProgress | None = None
    # `time.monotonic()` at start; `duration` is set once the run ends.
    started_at: float | None = None
    duration: float | None = None

    @property
    def elapsed(self) -> float:
        """Seconds since the current (or last) run started - frozen at
        `duration` once it has ended."""
        if self.duration is not None:
            return self.duration
        return time.monotonic() - self.started_at if self.started_at is not None else 0.0

    async def run(self, command: list[str], on_output: Callable[[], None]) -> None:
        """Runs `command` as a subprocess, streaming its combined
        stdout/stderr into `self.lines` line by line as it produces them -
        except `PROGRESS` lines, which update `self.progress` instead.
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
        self.progress = None
        self.started_at = time.monotonic()
        self.duration = None
        on_output()

        try:
            self.return_code = await self._stream(command, on_output)
        except Exception as exc:
            # Never leave the job stuck "running" - report why it failed instead.
            logger.exception("Admin job %s failed to run", command)
            self.lines.append(f"{type(exc).__name__}: {exc}")
            self.return_code = -1
        finally:
            self.duration = time.monotonic() - self.started_at
            self.is_running = False
            on_output()

    async def _stream(self, command: list[str], on_output: Callable[[], None]) -> int:
        """Starts `command` and feeds its output lines into `lines`/
        `progress` until it exits.

        Deliberately `subprocess.Popen` plus a reader thread, not
        `asyncio.create_subprocess_exec`: on Windows, uvicorn's `--reload`
        runs the app on a `SelectorEventLoop`, which can't start
        subprocesses at all (`NotImplementedError`) - the job then never
        started and sat on "running" forever.

        Args:
            command: Argv to run.
            on_output: Called after every new line.

        Returns:
            The process's exit code.
        """
        process = subprocess.Popen(
            command,
            cwd=str(REPO_ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            # The decode below assumes UTF-8; on Windows a piped child would
            # otherwise write in the ANSI code page and garble Czech names.
            env={**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUNBUFFERED": "1"},
        )
        assert process.stdout is not None
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[bytes | None] = asyncio.Queue()

        def _pump() -> None:
            try:
                for raw_line in process.stdout:
                    loop.call_soon_threadsafe(queue.put_nowait, raw_line)
            finally:
                loop.call_soon_threadsafe(queue.put_nowait, None)

        threading.Thread(target=_pump, daemon=True).start()
        while (raw_line := await queue.get()) is not None:
            line = raw_line.decode("utf-8", errors="replace").rstrip()
            progress = parse_progress(line)
            if progress is not None:
                self.progress = progress
            else:
                self.lines.append(line)
            on_output()

        return await asyncio.to_thread(process.wait)


def _sources_table() -> None:
    """Lists every configured OEM source (active or not) - brand, parser,
    model coverage - read straight from `config/sources.yaml`.
    """
    sources = SourceRegistry().load_all()
    with ui.column().classes("w-full gap-2"):
        ui.label(t("admin.sources")).classes("text-[13px] font-bold uppercase tracking-wide text-subtext")
        with ui.column().classes("w-full gap-1.5"):
            for source in sources:
                _source_row(source)


def _source_row(source: Source) -> None:
    """One line in the sources list.

    Args:
        source: The source to render.
    """
    status_classes = "rounded-full px-2.5 py-1 text-[11px] font-semibold " + (
        "bg-accent-soft text-accent" if source.active else "bg-panel-2 text-subtext"
    )
    with ui.row().classes("w-full items-center gap-3 rounded-control border border-border bg-panel px-3.5 py-2.5"):
        ui.label(t("admin.active") if source.active else t("admin.inactive")).classes(status_classes)
        with ui.column().classes("gap-0"):
            ui.label(f"{source.brand} ({source.parser_key})").classes("text-[13px] font-semibold text-text")
            ui.label(", ".join(source.models) or "—").classes("text-[11.5px] text-subtext")


def _last_duration(job_key: str) -> float | None:
    """Args:
        job_key: The job's key (see `_job_section`).

    Returns:
        Seconds the job's last successful run took, if one was recorded.
    """
    return app.storage.general.get(LAST_DURATIONS_KEY, {}).get(job_key)


def _save_duration(job_key: str, seconds: float) -> None:
    """Records `seconds` as the job's last successful run time.

    Args:
        job_key: The job's key (see `_job_section`).
        seconds: How long the run took.
    """
    durations = dict(app.storage.general.get(LAST_DURATIONS_KEY, {}))
    durations[job_key] = seconds
    app.storage.general[LAST_DURATIONS_KEY] = durations


def _job_section(
    job_key: str,
    title: str,
    description: str,
    state: JobState,
    command: list[str],
    is_authorized: Callable[[], Awaitable[bool]],
) -> None:
    """Builds one job's UI: a button, a progress bar with elapsed time and
    an estimate of the time left, and a scrollable, live output log.

    Args:
        job_key: Stable identifier the job's last run time is stored under.
        title: Heading shown above the button.
        description: One-line explanation of what running this does.
        state: The job's `JobState` - fresh per page load (see `admin`).
        command: Argv to run when the button is clicked.
        is_authorized: Re-checks admin rights at click time - see the
            module docstring.
    """
    with ui.column().classes("w-full gap-2.5 rounded-card border border-border bg-panel p-4 shadow-card"):
        ui.label(title).classes("text-[15px] font-bold text-text")
        ui.label(description).classes("text-[12.5px] text-subtext")

        def on_output() -> None:
            status.refresh()
            content.refresh()

        async def start() -> None:
            if not await is_authorized():
                return
            await state.run(command, on_output)
            if state.return_code == 0 and state.duration is not None:
                _save_duration(job_key, state.duration)
                status.refresh()

        @ui.refreshable
        def status() -> None:
            """Progress bar + timing - refreshed on every output line and
            once a second by the timer below, without rebuilding the log."""
            last_duration = _last_duration(job_key)
            if not state.is_running:
                if last_duration is not None:
                    ui.label(t("admin.progress.lastRun", duration=format_duration(last_duration))).classes(
                        "text-[12px] text-subtext"
                    )
                return

            fraction = state.progress.fraction if state.progress is not None else 0.0
            ui.linear_progress(value=fraction, show_value=False, size="8px").props("rounded").classes("w-full").mark(
                "job-progress"
            )
            with ui.row().classes("w-full items-center justify-between gap-2"):
                if state.progress is not None:
                    progress = state.progress
                    text = t("admin.progress.step", step=progress.step, steps=progress.steps, item=progress.item)
                    if progress.sub is not None and progress.subs:
                        text += " " + t("admin.progress.sub", sub=progress.sub, subs=progress.subs)
                else:
                    text = t("admin.progress.starting")
                ui.label(text).classes("text-[12px] font-semibold text-text")

                timing = t("admin.progress.elapsed", elapsed=format_duration(state.elapsed))
                remaining = estimate_remaining(state.elapsed, fraction, last_duration)
                if remaining is not None:
                    timing += " · " + t("admin.progress.remaining", remaining=format_duration(remaining))
                ui.label(timing).classes("text-[12px] text-subtext")

        status()
        ui.timer(1.0, lambda: status.refresh() if state.is_running else None)

        @ui.refreshable
        def content() -> None:
            with ui.row().classes("items-center gap-2.5"):
                button = (
                    ui.button(
                        t("admin.running") if state.is_running else t("admin.run"),
                        on_click=start,
                    )
                    .props("no-caps unelevated")
                    .classes("rounded-control bg-accent px-4 py-2 text-[13px] font-semibold text-accent-text")
                    .mark(f"run-{job_key}")
                )
                button.set_enabled(not state.is_running)
                if state.return_code is not None:
                    ok = state.return_code == 0
                    ui.label(t("admin.done") if ok else t("admin.failed", code=state.return_code)).classes(
                        "text-[12.5px] font-semibold " + ("text-accent" if ok else "text-flag")
                    )

            if state.lines:
                with ui.scroll_area().classes(
                    "h-[240px] w-full rounded-control border border-border bg-panel-2 p-2.5"
                ) as log_area:
                    ui.label("\n".join(state.lines)).classes("whitespace-pre-wrap font-mono text-[11.5px] text-text")
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
        ui.label(t("admin.title")).classes("text-xl font-bold text-text")
        if auth_state.user is None:
            ui.label(t("auth.adminOnly")).classes("text-[13px] text-subtext")
            ui.button(t("header.login"), icon="login", on_click=open_login_dialog).props("no-caps unelevated").classes(
                "rounded-control bg-accent px-3.5 py-2 text-[13px] font-semibold text-accent-text"
            ).mark("login")
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

        # Read once: the panels below are built over several awaits, during
        # which a `still_admin` check (e.g. the AI trace's timer) refreshes
        # `auth_state` and briefly leaves `auth_state.user` unset.
        admin_id = auth_state.user.id
        scraper_state = JobState()
        import_state = JobState()
        client = ui.context.client
        # One check at a time per page: the trace tab's timer and a click can
        # ask at the same moment, and both would refresh `auth_state`.
        admin_check = asyncio.Lock()

        async def still_admin() -> bool:
            """Re-reads the session's user from the database (see the module
            docstring); on "no", reloads the page into the "no rights" view."""
            async with admin_check:
                await auth_state.refresh()
            if auth_state.is_admin:
                return True
            with client:
                ui.navigate.reload()
            return False

        with ui.column().classes("min-h-screen w-full bg-bg text-text gap-6 p-8"):
            with ui.row().classes("w-full items-center justify-between"):
                ui.label(t("admin.title")).classes("text-xl font-bold text-text")
                ui.link(t("auth.backToApp"), "/").classes("text-[13px] text-accent")

            with ui.tabs().props("no-caps align=left").classes("text-text") as tabs:
                data_tab = ui.tab(t("admin.tabs.data"))
                controls_tab = ui.tab(t("admin.tabs.controls"))
                trace_tab = ui.tab(t("admin.tabs.aiTrace"))
                authors_tab = ui.tab(t("admin.tabs.authors"))
                new_feedback = await feedback_state.count_new(admin_id)
                feedback_tab = ui.tab(
                    t("admin.tabs.feedbackNew", count=new_feedback.value)
                    if new_feedback.ok and new_feedback.value
                    else t("admin.tabs.feedback")
                ).mark("feedback-tab")
                comparisons_tab = ui.tab(t("admin.tabs.comparisons")).mark("comparisons-tab")

            with ui.tab_panels(tabs, value=data_tab).classes("w-full bg-transparent"):
                with ui.tab_panel(data_tab).classes("p-0"):
                    _data_panel()
                with ui.tab_panel(controls_tab).classes("p-0"):
                    _controls_panel(scraper_state, import_state, still_admin)
                with ui.tab_panel(trace_tab).classes("p-0"):
                    with ui.column().classes("w-full max-w-[1100px]"):
                        llm_trace_panel(still_admin)
                with ui.tab_panel(authors_tab).classes("p-0"):
                    await authors_admin_panel(admin_id)
                with ui.tab_panel(feedback_tab).classes("p-0"):
                    await feedback_admin_panel(admin_id)
                with ui.tab_panel(comparisons_tab).classes("p-0"):
                    load_comparison_stats = await comparison_stats_admin_panel(admin_id)

            async def on_tab_change(event: ValueChangeEventArguments) -> None:
                if event.value in (comparisons_tab, comparisons_tab.props["name"]):
                    await load_comparison_stats()

            tabs.on_value_change(on_tab_change)


def _data_panel() -> None:
    """The "Data" tab: the configured sources, read-only."""
    with ui.column().classes("w-full max-w-[720px] gap-6"):
        _sources_table()


def _controls_panel(
    scraper_state: JobState, import_state: JobState, is_authorized: Callable[[], Awaitable[bool]]
) -> None:
    """The "Ovládání" (Controls) tab: the scraper and import jobs.

    Args:
        scraper_state: State of the scraper job (fresh per page load).
        import_state: State of the catalog import job (fresh per page load).
        is_authorized: Re-checks admin rights at click time - see the
            module docstring.
    """
    with ui.column().classes("w-full max-w-[720px] gap-6"):
        _job_section(
            "scraper",
            t("admin.jobs.scraper.title"),
            t("admin.jobs.scraper.description"),
            scraper_state,
            SCRAPER_COMMAND,
            is_authorized,
        )
        _job_section(
            "import",
            t("admin.jobs.import.title"),
            t("admin.jobs.import.description"),
            import_state,
            IMPORT_COMMAND,
            is_authorized,
        )

"""An admin page that is already open must stop working once the account
loses admin rights: the job buttons and the AI trace's refresh/clear
re-check rights against the database when they act (see the module
docstring of app/ui/admin.py), instead of trusting the check made when the
page was built.
"""

import asyncio
from datetime import datetime
from pathlib import Path

import pytest
from nicegui.testing import User
from sqlalchemy import update
from sqlalchemy.orm import Session

from app.ai.trace import trace_log
from app.models.user import User as UserRow

pytestmark = [
    pytest.mark.usefixtures("patch_ui_session"),
    pytest.mark.nicegui_main_file(str(Path(__file__).with_name("_user_main.py"))),
]

EMAIL = "boss@example.cz"


@pytest.fixture(autouse=True)
def _empty_trace_log():
    trace_log.clear()
    yield
    trace_log.clear()


@pytest.fixture()
def job_runs(user: User, monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    """Records job starts instead of spawning the scraper/import. Patched
    by dotted path after the `user` fixture is up: that fixture re-imports
    the app's modules, so a `JobState` imported at the top of this file
    can be a different class from the one the page uses."""
    runs: list[list[str]] = []

    async def _record(self, command: list[str], on_output) -> None:
        runs.append(command)

    monkeypatch.setattr("app.ui.admin.JobState.run", _record)
    return runs


def _demote(session: Session) -> None:
    session.execute(update(UserRow).where(UserRow.email == EMAIL).values(is_admin=False))
    session.commit()


def _record_call(marker: str) -> None:
    trace_log.record(
        started_at=datetime.now().astimezone(),
        provider="groq",
        model="openai/gpt-oss-120b",
        request={"messages": [{"role": "user", "content": marker}]},
        response={},
        reply_text="{}",
        duration_ms=1.0,
        input_tokens=1,
        output_tokens=1,
    )


async def _wait_for(condition, seconds: float = 3.0) -> bool:
    for _ in range(int(seconds / 0.05)):
        if condition():
            return True
        await asyncio.sleep(0.05)
    return condition()


async def _open_console(user: User, log_in) -> None:
    await user.open("/")
    await log_in(user, EMAIL, admin=True)
    await user.open("/admin")


async def test_admin_can_start_a_job(user: User, log_in, job_runs: list[list[str]]) -> None:
    await _open_console(user, log_in)
    user.find("Ovládání").click()
    user.find(marker="run-scraper").click()
    assert await _wait_for(lambda: job_runs)


async def test_demoted_admin_cannot_start_a_job_from_an_open_page(
    user: User, log_in, job_runs: list[list[str]], patch_ui_session: Session
) -> None:
    await _open_console(user, log_in)
    user.find("Ovládání").click()

    _demote(patch_ui_session)
    user.find(marker="run-scraper").click()
    await user.should_see("Tato stránka je jen pro administrátory.", retries=50)
    assert job_runs == []


async def test_demoted_admin_gets_no_new_trace_entries(user: User, log_in, patch_ui_session: Session) -> None:
    await _open_console(user, log_in)
    user.find("AI komunikace").click()

    _demote(patch_ui_session)
    # The live-refresh timer picks the new entry up on its own; it must
    # re-check rights before sending it.
    _record_call("SECRET-CHAT-TEXT")
    await user.should_see("Tato stránka je jen pro administrátory.", retries=50)
    await user.should_not_see("SECRET-CHAT-TEXT")

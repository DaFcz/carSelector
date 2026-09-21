"""Fixtures for the UI test suite. Reuses `tests/conftest.py`'s seeded
in-memory database (real service calls against deterministic seed data,
same as the API test suite) by monkeypatching `app.ui.db.get_session` to
yield it - there's no wire format to fake here, unlike the former
frontend's `vi.mock('../api/*')`.
"""

from collections.abc import Generator
from contextlib import contextmanager

import pytest
from nicegui.testing import User
from sqlalchemy.orm import Session

import app.ui.db as ui_db
from app.core import config
from app.services.auth import auth_service
from app.services.mailer import EmailSender
from tests.conftest import SeededData, seeded_session  # noqa: F401 - re-exported fixture


@pytest.fixture()
def patch_ui_session(seeded_session: SeededData, monkeypatch: pytest.MonkeyPatch) -> Session:
    """Makes every `app.ui.db.get_session()` call in the UI layer yield
    the same seeded session `seeded_session` provides to the API test
    suite, instead of opening a real connection to `DATABASE_URL`.

    `app/ui/state.py` calls this via `ui_db.get_session()` (a module
    attribute lookup at call time), not a `from app.ui.db import
    get_session` copy - patching the attribute here is what makes that
    lookup pick up the fake.

    Args:
        seeded_session: The seeded in-memory session (see `tests/conftest.py`).
        monkeypatch: Standard pytest fixture, undoes the patch after the test.

    Returns:
        The same `Session` `app.ui.db.get_session()` now yields.
    """

    @contextmanager
    def _fake_get_session() -> Generator[Session, None, None]:
        yield seeded_session.session

    monkeypatch.setattr(ui_db, "get_session", _fake_get_session)
    return seeded_session.session


class CodeInbox(EmailSender):
    """Replaces the real email sender, so UI tests can read the login code
    that would have been emailed.
    """

    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []

    def send_login_code(self, to_address: str, code: str, ttl_minutes: int) -> None:
        self.sent.append((to_address, code))

    @property
    def last_code(self) -> str:
        return self.sent[-1][1]


@pytest.fixture()
def inbox(monkeypatch: pytest.MonkeyPatch) -> CodeInbox:
    """Routes `auth_service`'s outgoing login codes into a `CodeInbox`."""
    box = CodeInbox()
    monkeypatch.setattr(auth_service, "_email_sender", box)
    return box


@pytest.fixture()
def log_in(inbox: CodeInbox, monkeypatch: pytest.MonkeyPatch):
    """Returns `async log_in(user, email, *, admin=False, expect="Odhlásit")`:
    drives the header's login dialog end to end (email -> emailed code ->
    confirm), exactly as a person would. `admin=True` first lists the
    address in `ADMIN_EMAILS`, the only way an account becomes admin on
    first login. `expect` is the text to wait for as proof the login
    finished (the header's logout button, unless the page has none - e.g.
    `/admin`, which reloads into the console).
    """

    async def _log_in(user: User, email: str, *, admin: bool = False, expect: str = "Odhlásit") -> None:
        if admin:
            monkeypatch.setattr(config, "ADMIN_EMAILS", frozenset({email}))
        user.find("Přihlásit se").click()
        await user.should_see("Přihlášení")
        user.find("E-mail").type(email)
        user.find("Poslat kód").click()
        await user.should_see("Poslali jsme šestimístný kód")
        user.find("Kód z e-mailu").type(inbox.last_code)
        user.find("Potvrdit").click()
        # The DB call runs in a thread, so wait (generously) for the page to
        # show what a finished login changes. NiceGUI's test simulation can't
        # be asked "is the dialog gone" - it still reports a closed dialog's
        # content as visible - hence a positive signal instead.
        await user.should_see(expect, retries=100)

    return _log_in

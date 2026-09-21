"""Drives the email-code login and the admin wall through NiceGUI's
headless `user` fixture. Codes are read from `inbox` (see conftest.py)
instead of a real mailbox.
"""

from pathlib import Path

import pytest
from nicegui.testing import User
from sqlalchemy.orm import Session

from app.ai import client as client_module
from app.core import config
from app.models.user import User as UserRow
from tests.ui.conftest import CodeInbox

pytestmark = [
    pytest.mark.usefixtures("patch_ui_session"),
    pytest.mark.nicegui_main_file(str(Path(__file__).with_name("_user_main.py"))),
]

ADMIN_CONSOLE_MARKER = "1. Spustit scraper"


@pytest.fixture(autouse=True)
def _no_key(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(client_module, "AI_PROVIDER", "groq")
    monkeypatch.setattr(client_module, "GROQ_API_KEY", None)
    client_module.set_runtime_api_key(None)
    yield
    client_module.set_runtime_api_key(None)


async def test_anonymous_visitor_sees_login_but_no_admin_controls(user: User) -> None:
    await user.open("/")

    await user.should_see("Přihlásit se")
    await user.should_see("Průvodce výběrem")  # the app itself stays open without login
    await user.should_not_see("Admin")
    await user.should_not_see("AI klíč")
    await user.should_not_see("Odhlásit")


async def test_regular_user_logs_in_but_gets_no_admin_controls(user: User, log_in) -> None:
    await user.open("/")
    await log_in(user, "jana@example.cz")

    await user.should_see("Odhlásit")
    await user.should_not_see("Přihlásit se")
    await user.should_not_see("Admin")
    await user.should_not_see("AI klíč")


async def test_admin_sees_admin_link_and_api_key_button(user: User, log_in) -> None:
    await user.open("/")
    await log_in(user, "boss@example.cz", admin=True)

    await user.should_see("Admin")
    await user.should_see("AI klíč chybí")


async def test_login_survives_a_page_reload(user: User, log_in) -> None:
    await user.open("/")
    await log_in(user, "jana@example.cz")

    await user.open("/")
    await user.should_see("jana@example.cz")
    await user.should_see("Odhlásit")


async def test_logout_returns_to_anonymous(user: User, log_in) -> None:
    await user.open("/")
    await log_in(user, "boss@example.cz", admin=True)

    user.find("Odhlásit").click()

    await user.should_see("Přihlásit se")
    await user.should_not_see("AI klíč")
    await user.open("/")
    await user.should_see("Přihlásit se")  # and the session is really gone, not just hidden


async def test_wrong_code_is_rejected_and_login_does_not_happen(user: User, inbox: CodeInbox) -> None:
    await user.open("/")
    user.find("Přihlásit se").click()
    user.find("E-mail").type("jana@example.cz")
    user.find("Poslat kód").click()
    await user.should_see("Poslali jsme šestimístný kód")

    user.find("Kód z e-mailu").type("000000" if inbox.last_code != "000000" else "111111")
    user.find("Potvrdit").click()

    await user.should_see("Kód není správný")
    await user.should_not_see("Odhlásit")


async def test_invalid_email_is_rejected(user: User, inbox: CodeInbox) -> None:
    await user.open("/")
    user.find("Přihlásit se").click()
    user.find("E-mail").type("not-an-email")
    user.find("Poslat kód").click()

    await user.should_see("platnou e-mailovou adresu")
    assert inbox.sent == []


async def test_deactivated_account_is_logged_out_on_next_page_load(
    user: User, log_in, patch_ui_session: Session
) -> None:
    await user.open("/")
    await log_in(user, "jana@example.cz")

    row = patch_ui_session.query(UserRow).filter_by(email="jana@example.cz").one()
    row.is_active = False
    patch_ui_session.commit()

    await user.open("/")
    await user.should_see("Přihlásit se")
    await user.should_not_see("jana@example.cz")


async def test_demoted_admin_loses_admin_controls_on_next_page_load(
    user: User, log_in, patch_ui_session: Session
) -> None:
    await user.open("/")
    await log_in(user, "boss@example.cz", admin=True)

    row = patch_ui_session.query(UserRow).filter_by(email="boss@example.cz").one()
    row.is_admin = False
    patch_ui_session.commit()

    await user.open("/")
    await user.should_see("boss@example.cz")
    await user.should_not_see("AI klíč")
    await user.open("/admin")
    await user.should_not_see(ADMIN_CONSOLE_MARKER)


async def test_expired_session_is_dropped(user: User, log_in, monkeypatch: pytest.MonkeyPatch) -> None:
    await user.open("/")
    await log_in(user, "jana@example.cz")

    monkeypatch.setattr(config, "AUTH_SESSION_DAYS", -1)

    await user.open("/")
    await user.should_see("Přihlásit se")


async def test_admin_page_shows_login_prompt_to_anonymous_visitors(user: User) -> None:
    await user.open("/admin")

    await user.should_see("Tato stránka je jen pro administrátory.")
    await user.should_see("Přihlásit se")
    await user.should_not_see(ADMIN_CONSOLE_MARKER)
    await user.should_not_see("Spustit")


async def test_admin_page_refuses_regular_users(user: User, log_in) -> None:
    await user.open("/")
    await log_in(user, "jana@example.cz")

    await user.open("/admin")

    await user.should_see("nemá administrátorská práva")
    await user.should_not_see(ADMIN_CONSOLE_MARKER)
    await user.should_not_see("Spustit")


async def test_admin_page_opens_for_admins(user: User, log_in) -> None:
    await user.open("/")
    await log_in(user, "boss@example.cz", admin=True)

    await user.open("/admin")

    await user.should_see(ADMIN_CONSOLE_MARKER)


async def test_logging_in_from_the_admin_page_reveals_the_console(user: User, log_in) -> None:
    await user.open("/admin")
    await user.should_not_see(ADMIN_CONSOLE_MARKER)

    await log_in(user, "boss@example.cz", admin=True, expect=ADMIN_CONSOLE_MARKER)

"""Drives the header's API-key button and dialog through NiceGUI's headless
`user` fixture (no real browser); `_user_main.py` is the entry file that
fixture needs. The button and the dialog are admin-only, so every test that
uses them logs in as an admin first (see `log_in` in conftest.py).
"""

from pathlib import Path

import pytest
from nicegui import ui
from nicegui.testing import User

from app.ai import client as client_module

pytestmark = [
    pytest.mark.usefixtures("patch_ui_session"),
    pytest.mark.nicegui_main_file(str(Path(__file__).with_name("_user_main.py"))),
]


@pytest.fixture(autouse=True)
def _no_key(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(client_module, "AI_PROVIDER", "groq")
    monkeypatch.setattr(client_module, "GROQ_API_KEY", None)
    client_module.set_runtime_api_key(None)
    yield
    client_module.set_runtime_api_key(None)


ADMIN = "boss@example.cz"


async def test_entering_key_in_dialog_configures_ai(user: User, log_in) -> None:
    await user.open("/")
    await log_in(user, ADMIN, admin=True)
    await user.should_see("AI klíč chybí")

    user.find("AI klíč chybí").click()
    await user.should_see("API klíč pro AI")
    user.find(kind=ui.input).type("gsk-typed-in-ui")
    user.find("Uložit").click()

    await user.should_see("AI klíč")
    await user.should_not_see("AI klíč chybí")
    assert client_module.is_configured()


async def test_blank_key_is_rejected(user: User, log_in) -> None:
    await user.open("/")
    await log_in(user, ADMIN, admin=True)
    user.find("AI klíč chybí").click()
    user.find("Uložit").click()

    await user.should_see("Zadejte prosím klíč.")
    assert not client_module.is_configured()


async def test_rejected_key_shows_specific_message_in_chat(
    user: User, log_in, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.ai.errors import AiProviderError
    from app.ui import state as state_module

    def _reject(*_args, **_kwargs):
        raise AiProviderError("ai_invalid_key", "Invalid API Key")

    monkeypatch.setattr(state_module.orchestrator, "handle_message", _reject)
    await user.open("/")
    await log_in(user, ADMIN, admin=True)
    user.find("Napište odpověď…").type("Chci rodinné auto do 900 tisíc.").trigger("keydown.enter")

    await user.should_see("AI služba odmítla API klíč")
    await user.should_not_see("Něco se nepovedlo")


async def test_key_with_diacritics_is_rejected_with_explanation(user: User, log_in) -> None:
    await user.open("/")
    await log_in(user, ADMIN, admin=True)
    user.find("AI klíč chybí").click()
    user.find(kind=ui.input).type("gsk_věc")
    user.find("Uložit").click()

    await user.should_see("nepovolený znak „ě“ na pozici 6")
    assert not client_module.is_configured()


async def test_rejected_key_tells_non_admins_to_contact_the_administrator(
    user: User, log_in, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.ai.errors import AiProviderError
    from app.ui import state as state_module

    def _reject(*_args, **_kwargs):
        raise AiProviderError("ai_invalid_key", "Invalid API Key")

    monkeypatch.setattr(state_module.orchestrator, "handle_message", _reject)
    await user.open("/")
    await log_in(user, "jana@example.cz")
    user.find("Napište odpověď…").type("Chci rodinné auto do 900 tisíc.").trigger("keydown.enter")

    await user.should_see("Dejte prosím vědět administrátorovi")
    await user.should_not_see("tlačítko „AI klíč“")


async def test_forged_save_event_from_a_non_admin_does_not_change_the_key(user: User) -> None:
    """The dialog's elements exist on every visitor's page even though the
    header never offers the button - a browser can still send a click for
    one over the websocket, so the handler itself has to refuse.
    """
    await user.open("/")
    await user.should_not_see("AI klíč chybí")  # no way to open it in the UI...

    user.find(kind=ui.input, content="API klíč").type("gsk-forged-by-anonymous")  # ...but the elements are there
    user.find("Uložit").click()

    assert not client_module.is_configured()

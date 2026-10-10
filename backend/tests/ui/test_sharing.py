"""Sharing through NiceGUI's `user` fixture: the "Sdílet" buttons open the
share dialog with a link and QR code, and the link's public page shows the
frozen result - or a "link expired" message."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from nicegui.testing import User

from app.ai import client as client_module
from app.core import config
from app.services import catalog, sharing
from tests.conftest import SeededData

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


def _share_url(user: User) -> str:
    (field,) = user.find(marker="share-url").elements
    return field.value


async def test_share_results_opens_dialog_with_link_and_qr(user: User) -> None:
    await user.open("/")
    await user.should_see("v katalogu", retries=100)

    user.find(marker="share-results").click()
    await user.should_see("Sdílet výběr", retries=100)

    assert "/s/" in _share_url(user)
    await user.should_see(marker="share-qr")


async def test_share_from_vehicle_detail(user: User, seeded_session: SeededData) -> None:
    await user.open("/")
    await user.should_see("v katalogu", retries=100)
    user.find(marker=f"car-{seeded_session.config_rline_awd_id}").click()
    await user.should_see("Stáhnout PDF", retries=100)

    user.find(marker="share-vehicle").click()
    await user.should_see("Sdílet výběr", retries=100)

    token = _share_url(user).rsplit("/s/", 1)[1]
    snapshot = sharing.get(seeded_session.session, token)
    assert snapshot is not None
    assert [v.configuration_id for v in snapshot.content.vehicles] == [seeded_session.config_rline_awd_id]


async def test_shared_page_shows_frozen_cars(user: User, seeded_session: SeededData) -> None:
    car = catalog.list_vehicles(seeded_session.session).items[0]
    snapshot = sharing.create(seeded_session.session, [], [car])

    await user.open(f"/s/{snapshot.token}")

    await user.should_see("Sdílený výběr: 1 vůz")
    await user.should_see(f"{car.brand} {car.model} {car.trim}")
    await user.should_see("Najít vlastní auto")


async def test_expired_link_shows_message(user: User, seeded_session: SeededData) -> None:
    car = catalog.list_vehicles(seeded_session.session).items[0]
    long_ago = datetime.now(UTC) - timedelta(days=config.SHARE_TTL_DAYS + 1)
    snapshot = sharing.create(seeded_session.session, [], [car], now=long_ago)

    await user.open(f"/s/{snapshot.token}")

    await user.should_see("Odkaz neexistuje nebo už vypršel.")
    await user.should_not_see(f"{car.brand} {car.model}")

"""The detail dialog's "Stáhnout PDF" button through NiceGUI's `user`
fixture: open a card's detail, click the button, get a PDF download."""

from pathlib import Path

import pytest
from nicegui.testing import User

from tests.conftest import SeededData

pytestmark = [
    pytest.mark.usefixtures("patch_ui_session"),
    pytest.mark.nicegui_main_file(str(Path(__file__).with_name("_user_main.py"))),
]


async def test_detail_dialog_downloads_pdf(user: User, seeded_session: SeededData) -> None:
    await user.open("/")
    await user.should_see("v katalogu", retries=100)

    user.find(marker=f"car-{seeded_session.config_rline_awd_id}").click()
    await user.should_see("Stáhnout PDF", retries=100)

    user.find(marker="export-pdf").click()
    response = await user.download.next(timeout=10)

    assert response.content.startswith(b"%PDF")

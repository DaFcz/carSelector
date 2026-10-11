"""The comparison statistic end to end: opening a comparison counts it
(once per distinct pick), and the admin console's "Porovnání" tab shows
the most compared models with their partners.
"""

from pathlib import Path

import pytest
from nicegui.testing import User
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.comparison_view import ComparisonView
from tests.conftest import SeededData

pytestmark = [
    pytest.mark.usefixtures("patch_ui_session"),
    pytest.mark.nicegui_main_file(str(Path(__file__).with_name("_user_main.py"))),
]


def _views(session: Session) -> int:
    return session.scalar(select(func.count(ComparisonView.id)))


async def test_shown_comparison_is_counted_once_and_listed_for_admin(
    user: User, seeded_session: SeededData, log_in
) -> None:
    session = seeded_session.session
    mazda, tiguan = seeded_session.config_prime_2wd_id, seeded_session.config_people_fwd_id
    await user.open("/")
    await user.should_see("v katalogu", retries=100)

    user.find(marker=f"compare-{mazda}").click()
    user.find(marker=f"compare-{tiguan}").click()
    await user.should_see("Porovnat (2)")
    user.find(marker="compare-open").click()
    await user.should_see(marker=f"compare-column-{tiguan}", retries=100)
    assert _views(session) == 1

    # Reopening the same pick isn't a new comparison.
    user.find(marker="compare-open").click()
    await user.should_see(marker=f"compare-column-{tiguan}", retries=100)
    assert _views(session) == 1

    await log_in(user, "boss@example.cz", admin=True)
    await user.open("/admin")
    # The tab loads on first open - wait until the page has wired that up.
    await user.should_see(marker="comparison-stats-period", retries=100)
    await user.should_not_see("Mazda CX-5")
    user.find(marker="comparisons-tab").click()
    await user.should_see("1 porovnání v období", retries=100)
    await user.should_see("Mazda CX-5")
    await user.should_see("Volkswagen Tiguan")
    await user.should_see("Nejčastěji srovnáván s")

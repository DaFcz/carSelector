"""app/services/sharing.py against the seeded in-memory database."""

from datetime import UTC, datetime, timedelta

import pytest

from app.core import config
from app.models.shared_snapshot import SharedSnapshot as SharedSnapshotRow
from app.schemas.requirement import UserRequirement
from app.services import catalog, sharing
from tests.conftest import SeededData

NOW = datetime(2026, 9, 25, 12, 0, tzinfo=UTC)
REQUIREMENT = UserRequirement(label="Rozpočet", value="do 900 000 Kč", source="„máme doma tři děti“", changed=True)


def _vehicles(seeded: SeededData):
    return catalog.list_vehicles(seeded.session).items


def test_create_then_get_round_trips_content(seeded_session: SeededData) -> None:
    vehicles = _vehicles(seeded_session)

    created = sharing.create(seeded_session.session, [REQUIREMENT], vehicles, now=NOW)
    loaded = sharing.get(seeded_session.session, created.token, now=NOW + timedelta(days=1))

    assert loaded is not None
    assert [v.configuration_id for v in loaded.content.vehicles] == [v.configuration_id for v in vehicles]
    assert loaded.content.vehicles[0].price == vehicles[0].price
    assert loaded.content.requirements[0].label == "Rozpočet"
    assert loaded.expires_at == NOW + timedelta(days=config.SHARE_TTL_DAYS)


def test_shared_content_never_includes_the_users_own_words_or_id(seeded_session: SeededData) -> None:
    created = sharing.create(seeded_session.session, [REQUIREMENT], _vehicles(seeded_session), user_id=None, now=NOW)

    row = seeded_session.session.query(SharedSnapshotRow).one()
    assert "tři děti" not in row.content_json
    assert "source" not in created.content.requirements[0].model_dump()


def test_tokens_are_random_and_long(seeded_session: SeededData) -> None:
    vehicles = _vehicles(seeded_session)
    tokens = {sharing.create(seeded_session.session, [], vehicles, now=NOW).token for _ in range(5)}

    assert len(tokens) == 5
    assert all(len(token) >= 22 for token in tokens)


def test_expired_and_unknown_tokens_return_none(seeded_session: SeededData) -> None:
    created = sharing.create(seeded_session.session, [], _vehicles(seeded_session), now=NOW)

    after_expiry = NOW + timedelta(days=config.SHARE_TTL_DAYS, seconds=1)
    assert sharing.get(seeded_session.session, created.token, now=after_expiry) is None
    assert sharing.get(seeded_session.session, "does-not-exist", now=NOW) is None


def test_creating_purges_expired_snapshots(seeded_session: SeededData) -> None:
    vehicles = _vehicles(seeded_session)
    old = sharing.create(seeded_session.session, [], vehicles, now=NOW)

    sharing.create(seeded_session.session, [], vehicles, now=NOW + timedelta(days=config.SHARE_TTL_DAYS + 1))

    tokens = {row.token for row in seeded_session.session.query(SharedSnapshotRow)}
    assert old.token not in tokens
    assert len(tokens) == 1


def test_caps_the_number_of_vehicles(seeded_session: SeededData) -> None:
    vehicles = _vehicles(seeded_session)
    many = [vehicles[0]] * (sharing.MAX_SHARED_VEHICLES + 5)

    created = sharing.create(seeded_session.session, [], many, now=NOW)

    assert len(created.content.vehicles) == sharing.MAX_SHARED_VEHICLES


def test_empty_vehicle_list_is_rejected(seeded_session: SeededData) -> None:
    with pytest.raises(ValueError):
        sharing.create(seeded_session.session, [], [], now=NOW)

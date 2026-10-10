"""Read-only shared snapshots of a result (see `app/models/shared_snapshot.py`).

Anyone can create one, logged in or not, and anyone with the link can read
it until it expires. Nothing in the stored content identifies the author:
requirement lines are stripped of the user's own chat words, and the
author's user id (if any) never leaves this module.
"""

import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core import config
from app.models.shared_snapshot import SharedSnapshot as SharedSnapshotRow
from app.schemas.requirement import UserRequirement
from app.schemas.sharing import SharedRequirement, SharedSnapshot, SharedSnapshotContent
from app.schemas.vehicle import VehicleSummary

# Enough for "the top of the list" without letting one link carry an
# arbitrarily large copy of the catalog.
MAX_SHARED_VEHICLES = 10
# 16 random bytes = 128 bits -> 22 URL-safe characters.
_TOKEN_BYTES = 16


def _now() -> datetime:
    return datetime.now(UTC)


def _aware(value: datetime) -> datetime:
    """SQLite hands `DateTime(timezone=True)` back naive; the stored values
    are always UTC, so re-attach it before comparing."""
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def create(
    db: Session,
    requirements: list[UserRequirement],
    vehicles: list[VehicleSummary],
    user_id: int | None = None,
    now: datetime | None = None,
) -> SharedSnapshot:
    """Stores a snapshot and returns it with its new token. Also deletes
    already-expired snapshots, so the table doesn't grow forever.

    Args:
        db: Session to write through; committed here.
        requirements: The requirement lines to show (their `source` and
            `changed` are dropped, see `SharedRequirement`).
        vehicles: Cars to show, in display order; only the first
            `MAX_SHARED_VEHICLES` are kept.
        user_id: The sharing user, if logged in - stored, never shown.
        now: Current time (a parameter so tests control expiry).

    Returns:
        The stored snapshot.

    Raises:
        ValueError: If `vehicles` is empty - there'd be nothing to show.
    """
    if not vehicles:
        raise ValueError("a shared snapshot needs at least one vehicle")
    created_at = now or _now()
    content = SharedSnapshotContent(
        requirements=[SharedRequirement(label=req.label, value=req.value) for req in requirements],
        vehicles=vehicles[:MAX_SHARED_VEHICLES],
    )
    row = SharedSnapshotRow(
        token=secrets.token_urlsafe(_TOKEN_BYTES),
        content_json=content.model_dump_json(),
        created_by_user_id=user_id,
        created_at=created_at,
        expires_at=created_at + timedelta(days=config.SHARE_TTL_DAYS),
    )
    db.execute(delete(SharedSnapshotRow).where(SharedSnapshotRow.expires_at < created_at))
    db.add(row)
    db.commit()
    return SharedSnapshot(token=row.token, content=content, created_at=created_at, expires_at=row.expires_at)


def get(db: Session, token: str, now: datetime | None = None) -> SharedSnapshot | None:
    """Args:
        db: Session to read through.
        token: The token from the shared link.
        now: Current time (a parameter so tests control expiry).

    Returns:
        The snapshot, or `None` if the token is unknown or expired - the
        two look the same to a viewer on purpose.
    """
    row = db.scalar(select(SharedSnapshotRow).where(SharedSnapshotRow.token == token))
    if row is None or _aware(row.expires_at) <= (now or _now()):
        return None
    return SharedSnapshot(
        token=row.token,
        content=SharedSnapshotContent.model_validate_json(row.content_json),
        created_at=_aware(row.created_at),
        expires_at=_aware(row.expires_at),
    )

"""Persists a logged-in user's most recent `StructuredRequirements`
snapshot (see `app/models/saved_requirements.py`), so the "Technické
požadavky" drawer survives a page reload or a new login session instead
of always starting empty - `app/services/conversation.py`'s conversation
state is otherwise purely in-memory, keyed by a `conversation_id` a fresh
page load throws away. See `app/ui/state.py`'s `ConversationState` for
where this is loaded (on `begin()`), saved (after `send`/
`send_wizard_answers`), and cleared (`restart()`).
"""

from datetime import datetime, timezone

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.saved_requirements import SavedRequirements
from app.schemas.requirement import StructuredRequirements


def load(db: Session, user_id: int) -> StructuredRequirements | None:
    """Args:
        db: Session to read through.
        user_id: Whose saved requirements to load.

    Returns:
        The user's saved requirements, or `None` if they have none saved
        yet.
    """
    row = db.scalar(select(SavedRequirements).where(SavedRequirements.user_id == user_id))
    if row is None:
        return None
    return StructuredRequirements.model_validate_json(row.requirements_json)


def save(db: Session, user_id: int, requirements: StructuredRequirements) -> None:
    """Overwrites `user_id`'s saved snapshot with `requirements`, creating
    it on the first save.

    Args:
        db: Session to write through; committed here.
        user_id: Whose snapshot to save.
        requirements: The requirements to save.
    """
    row = db.scalar(select(SavedRequirements).where(SavedRequirements.user_id == user_id))
    payload = requirements.model_dump_json()
    now = datetime.now(timezone.utc)
    if row is None:
        db.add(SavedRequirements(user_id=user_id, requirements_json=payload, updated_at=now))
    else:
        row.requirements_json = payload
        row.updated_at = now
    db.commit()


def clear(db: Session, user_id: int) -> None:
    """Deletes `user_id`'s saved snapshot, if any - so starting a fresh
    conversation (`ConversationState.restart()`) also forgets the old
    requirements server-side, not just in this session's UI state.

    Args:
        db: Session to write through; committed here.
        user_id: Whose snapshot to delete.
    """
    db.execute(delete(SavedRequirements).where(SavedRequirements.user_id == user_id))
    db.commit()

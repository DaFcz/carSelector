"""Feedback from logged-in users (bug reports, ideas, praise, anything
else) and its handling by admins - see doc/po/Feedback-proposal.md,
variant A.

A one-way inbox: the user sends, an admin sorts it by status and keeps an
internal note. The user isn't told what happened (that's variant C).

Every admin action re-checks, against the DB, that the acting user is an
active admin - same as `app/services/authors.py`.

Retention: items are kept until deleted by hand; the plan is to drop
resolved ones after 12 months once there's a scheduled job to do it.
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.feedback import Feedback
from app.models.user import User
from app.schemas.feedback import FEEDBACK_STATUSES, FEEDBACK_TYPES, FeedbackContext, FeedbackRead

MAX_TEXT_LENGTH = 4000
MAX_NOTE_LENGTH = 4000
# Per user per rolling 24 hours - generous for real use, a ceiling for a
# stuck script or someone pasting into the dialog in a loop.
MAX_PER_DAY = 10


class FeedbackError(Exception):
    """A feedback action was refused.

    Attributes:
        code: One of `"empty_text"` | `"text_too_long"` | `"note_too_long"`
            | `"invalid_type"` | `"invalid_status"` | `"rate_limited"` |
            `"forbidden"` | `"not_found"`. Stable; the UI maps each to text
            under `feedback.errors`.
    """

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _now() -> datetime:
    return datetime.now(UTC)


def _to_read(item: Feedback, email: str) -> FeedbackRead:
    return FeedbackRead(
        id=item.id,
        user_id=item.user_id,
        email=email,
        type=item.type,
        text=item.text,
        context=FeedbackContext.model_validate_json(item.context_json or "{}"),
        language=item.language,
        status=item.status,
        admin_note=item.admin_note,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def _require_admin(db: Session, admin_id: int) -> None:
    admin = db.get(User, admin_id)
    if admin is None or not admin.is_active or not admin.is_admin:
        raise FeedbackError("forbidden")


def submit(
    db: Session, user_id: int, feedback_type: str, text: str, context: FeedbackContext, language: str
) -> FeedbackRead:
    """Stores one piece of feedback.

    Args:
        db: Session to write through; committed here.
        user_id: The sending (logged-in) user.
        feedback_type: One of `FEEDBACK_TYPES`.
        text: What they wrote.
        context: What they were looking at (see `FeedbackContext`).
        language: The UI language they wrote from.

    Returns:
        The stored item, status `"new"`.

    Raises:
        FeedbackError: `"invalid_type"`, `"empty_text"`, `"text_too_long"`,
            `"forbidden"` (unknown or deactivated account),
            `"rate_limited"` (`MAX_PER_DAY` reached).
    """
    body = text.strip()
    if feedback_type not in FEEDBACK_TYPES:
        raise FeedbackError("invalid_type")
    if not body:
        raise FeedbackError("empty_text")
    if len(body) > MAX_TEXT_LENGTH:
        raise FeedbackError("text_too_long")
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise FeedbackError("forbidden")
    recent = db.scalar(
        select(func.count())
        .select_from(Feedback)
        .where(Feedback.user_id == user_id, Feedback.created_at >= _now() - timedelta(days=1))
    )
    if recent >= MAX_PER_DAY:
        raise FeedbackError("rate_limited")

    item = Feedback(
        user_id=user_id,
        type=feedback_type,
        text=body,
        context_json=context.model_dump_json(exclude_none=True),
        language=language,
        status="new",
        admin_note="",
        created_at=_now(),
    )
    db.add(item)
    db.commit()
    return _to_read(item, user.email)


def list_for_admin(
    db: Session, admin_id: int, feedback_type: str | None = None, status: str | None = None
) -> list[FeedbackRead]:
    """Args:
        db: Session to read through.
        admin_id: The acting admin.
        feedback_type: Only this type, or `None` for all.
        status: Only this status, or `None` for all.

    Returns:
        Matching items, newest first.

    Raises:
        FeedbackError: `"forbidden"`.
    """
    _require_admin(db, admin_id)
    query = select(Feedback, User.email).join(User, User.id == Feedback.user_id)
    if feedback_type is not None:
        query = query.where(Feedback.type == feedback_type)
    if status is not None:
        query = query.where(Feedback.status == status)
    rows = db.execute(query.order_by(Feedback.created_at.desc(), Feedback.id.desc())).all()
    return [_to_read(item, email) for item, email in rows]


def count_new(db: Session, admin_id: int) -> int:
    """Args:
        db: Session to read through.
        admin_id: The acting admin.

    Returns:
        How many items nobody has looked at yet (status `"new"`).

    Raises:
        FeedbackError: `"forbidden"`.
    """
    _require_admin(db, admin_id)
    return db.scalar(select(func.count()).select_from(Feedback).where(Feedback.status == "new"))


def update(db: Session, admin_id: int, feedback_id: int, status: str, admin_note: str) -> FeedbackRead:
    """Sets an item's status and internal note.

    Args:
        db: Session to write through; committed here.
        admin_id: The acting admin.
        feedback_id: The item.
        status: One of `FEEDBACK_STATUSES`.
        admin_note: Replaces the previous note.

    Returns:
        The updated item.

    Raises:
        FeedbackError: `"forbidden"`, `"not_found"`, `"invalid_status"`,
            `"note_too_long"`.
    """
    _require_admin(db, admin_id)
    if status not in FEEDBACK_STATUSES:
        raise FeedbackError("invalid_status")
    note = admin_note.strip()
    if len(note) > MAX_NOTE_LENGTH:
        raise FeedbackError("note_too_long")
    item = db.get(Feedback, feedback_id)
    if item is None:
        raise FeedbackError("not_found")
    item.status = status
    item.admin_note = note
    item.updated_at = _now()
    item.updated_by_user_id = admin_id
    db.commit()
    return _to_read(item, db.get(User, item.user_id).email)

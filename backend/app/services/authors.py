"""The author role: a logged-in user asks for it, an admin approves or
rejects the request, and can later take the role away again.

Every admin action re-checks, against the DB, that the acting user is an
active admin - the UI only builds the admin controls for admins (see
`app/ui/admin.py`), but the check belongs where the change is made.
"""

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.article import Article
from app.models.author_request import AuthorRequest
from app.models.user import User
from app.schemas.article import AuthorRead, AuthorRequestRead

MAX_DISPLAY_NAME_LENGTH = 120
MAX_MESSAGE_LENGTH = 2000


class AuthorError(Exception):
    """An author-role action was refused.

    Attributes:
        code: One of `"invalid_name"` | `"message_too_long"` |
            `"already_author"` | `"already_pending"` | `"forbidden"` |
            `"not_found"` | `"already_decided"`. Stable; the UI maps each
            to text under `authors.errors`.
    """

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _now() -> datetime:
    return datetime.now(UTC)


def _to_read(request: AuthorRequest, email: str) -> AuthorRequestRead:
    return AuthorRequestRead(
        id=request.id,
        user_id=request.user_id,
        email=email,
        display_name=request.display_name,
        message=request.message,
        status=request.status,
        created_at=request.created_at,
        decided_at=request.decided_at,
    )


def _require_admin(db: Session, admin_id: int) -> User:
    admin = db.get(User, admin_id)
    if admin is None or not admin.is_active or not admin.is_admin:
        raise AuthorError("forbidden")
    return admin


def latest_request(db: Session, user_id: int) -> AuthorRequestRead | None:
    """Args:
        db: Session to read through.
        user_id: Whose request to load.

    Returns:
        The user's most recent request (any status), or `None` if they
        never asked.
    """
    row = db.execute(
        select(AuthorRequest, User.email)
        .join(User, User.id == AuthorRequest.user_id)
        .where(AuthorRequest.user_id == user_id)
        .order_by(AuthorRequest.created_at.desc(), AuthorRequest.id.desc())
        .limit(1)
    ).first()
    return _to_read(row[0], row[1]) if row else None


def request_role(db: Session, user_id: int, display_name: str, message: str = "") -> AuthorRequestRead:
    """Files a request for the author role.

    Args:
        db: Session to write through; committed here.
        user_id: The requesting (logged-in) user.
        display_name: The byline they want to publish under.
        message: Optional note for the admin.

    Returns:
        The new pending request.

    Raises:
        AuthorError: `"invalid_name"` (blank or too long),
            `"message_too_long"`, `"already_author"`, `"already_pending"`,
            `"forbidden"` (unknown or deactivated account).
    """
    name = display_name.strip()
    note = message.strip()
    if not name or len(name) > MAX_DISPLAY_NAME_LENGTH:
        raise AuthorError("invalid_name")
    if len(note) > MAX_MESSAGE_LENGTH:
        raise AuthorError("message_too_long")
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise AuthorError("forbidden")
    if user.is_author:
        raise AuthorError("already_author")
    latest = latest_request(db, user_id)
    if latest is not None and latest.status == "pending":
        raise AuthorError("already_pending")

    request = AuthorRequest(user_id=user_id, display_name=name, message=note, status="pending", created_at=_now())
    db.add(request)
    db.commit()
    return _to_read(request, user.email)


def list_pending(db: Session, admin_id: int) -> list[AuthorRequestRead]:
    """Args:
        db: Session to read through.
        admin_id: The acting admin.

    Returns:
        Every pending request, oldest first (first come, first served).

    Raises:
        AuthorError: `"forbidden"` if `admin_id` isn't an active admin.
    """
    _require_admin(db, admin_id)
    rows = db.execute(
        select(AuthorRequest, User.email)
        .join(User, User.id == AuthorRequest.user_id)
        .where(AuthorRequest.status == "pending")
        .order_by(AuthorRequest.created_at, AuthorRequest.id)
    ).all()
    return [_to_read(request, email) for request, email in rows]


def decide(db: Session, admin_id: int, request_id: int, approve: bool) -> None:
    """Approves (granting the role and the requested byline) or rejects a
    pending request.

    Args:
        db: Session to write through; committed here.
        admin_id: The acting admin.
        request_id: The request to decide.
        approve: `True` to grant the role, `False` to reject.

    Raises:
        AuthorError: `"forbidden"`, `"not_found"`, `"already_decided"`.
    """
    _require_admin(db, admin_id)
    request = db.get(AuthorRequest, request_id)
    if request is None:
        raise AuthorError("not_found")
    if request.status != "pending":
        raise AuthorError("already_decided")
    request.status = "approved" if approve else "rejected"
    request.decided_at = _now()
    request.decided_by_user_id = admin_id
    if approve:
        user = db.get(User, request.user_id)
        user.is_author = True
        user.display_name = request.display_name
    db.commit()


def list_authors(db: Session, admin_id: int) -> list[AuthorRead]:
    """Args:
        db: Session to read through.
        admin_id: The acting admin.

    Returns:
        Every user holding the author role, by email.

    Raises:
        AuthorError: `"forbidden"`.
    """
    _require_admin(db, admin_id)
    article_count = select(func.count()).select_from(Article).where(Article.author_id == User.id).scalar_subquery()
    rows = db.execute(
        select(User.id, User.email, User.display_name, article_count)
        .where(User.is_author.is_(True))
        .order_by(User.email)
    ).all()
    return [
        AuthorRead(user_id=uid, email=email, display_name=name, article_count=count) for uid, email, name, count in rows
    ]


def revoke(db: Session, admin_id: int, user_id: int) -> None:
    """Takes the author role away. Their already published articles stay
    readable (and keep their byline) - they just can't write or edit any
    more until the role is granted again.

    Args:
        db: Session to write through; committed here.
        admin_id: The acting admin.
        user_id: The author.

    Raises:
        AuthorError: `"forbidden"`, `"not_found"`.
    """
    _require_admin(db, admin_id)
    user = db.get(User, user_id)
    if user is None:
        raise AuthorError("not_found")
    user.is_author = False
    db.commit()

"""Passwordless login: a 6-digit one-time code sent by email.

Flow: `AuthService.request_code` emails a code; `AuthService.verify_code`
checks it and returns the user, creating the account on first login (there
is no separate signup - any email may create a regular account; admin
rights come only from `ADMIN_EMAILS` or another admin, see
`app/core/config.py`).

Codes are stored only as an HMAC (`app/core/config.py`'s `AUTH_SECRET`), are
single-use, expire after `LOGIN_CODE_TTL_MINUTES`, are burned after
`LOGIN_CODE_MAX_ATTEMPTS` wrong guesses (a 6-digit code is only 10^6
possibilities, so the attempt cap is what actually protects it), and
requesting a new code invalidates any earlier one for that address.

Timestamps are always UTC-aware when written and compared in SQL, never in
Python after a read: SQLite hands `DateTime(timezone=True)` columns back
naive, Postgres hands them back aware, and a Python-side comparison would
break on one of them.
"""

import hashlib
import hmac
import re
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from app.core import config
from app.models.login_code import LoginCode
from app.models.user import User
from app.schemas.auth import UserRead
from app.services.mailer import EmailDeliveryError, EmailSender, get_email_sender

# Deliberately loose (one "@", something on each side, a dot in the domain):
# real validation is "did the code arrive", and a strict regex only
# rejects legitimate addresses.
_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_MAX_EMAIL_LENGTH = 320
_CODE_LENGTH = 6
# Spent/expired codes are kept this long (for rate limiting they only need
# an hour), then purged opportunistically on the next request.
_PURGE_AFTER = timedelta(days=1)


class AuthError(Exception):
    """A login step failed in a way the user should be told about.

    Attributes:
        code: One of `"invalid_email"` | `"rate_limited"` |
            `"email_delivery_failed"` | `"invalid_code"` |
            `"too_many_attempts"` | `"account_disabled"`. Stable, safe to
            show to users (the UI maps each to Czech text). Wrong and
            expired/unknown codes are both `"invalid_code"` on purpose -
            distinguishing them tells an attacker nothing useful but
            costs nothing to avoid.
    """

    def __init__(self, code: str, message: str | None = None) -> None:
        """Args:
            code: See `code` above.
            message: Developer-facing detail for logs; defaults to `code`.
        """
        super().__init__(message or code)
        self.code = code


def normalize_email(raw: str) -> str:
    """Canonicalizes an email address so `users.email`'s plain unique
    constraint is effectively case-insensitive.

    Args:
        raw: The address as typed.

    Returns:
        Stripped and lowercased.

    Raises:
        AuthError: `"invalid_email"` - empty, too long, or not shaped
            like an address.
    """
    address = raw.strip().lower()
    if len(address) > _MAX_EMAIL_LENGTH or not _EMAIL_PATTERN.match(address):
        raise AuthError("invalid_email")
    return address


def _now() -> datetime:
    return datetime.now(timezone.utc)


class AuthService:
    """Issues and verifies login codes, and looks up users for sessions."""

    def __init__(self, email_sender: EmailSender | None = None) -> None:
        """Args:
            email_sender: How codes are delivered. Defaults to whatever
                `EMAIL_BACKEND` selects, built lazily on first use so
                importing this module never touches the mail config.
        """
        self._email_sender = email_sender

    def _sender(self) -> EmailSender:
        if self._email_sender is None:
            self._email_sender = get_email_sender()
        return self._email_sender

    @staticmethod
    def _hash_code(address: str, code: str) -> str:
        """Keyed hash of `code`, bound to `address` so a leaked hash for
        one address can't be replayed against another.

        Args:
            address: Normalized email the code was issued for.
            code: The plaintext code.

        Returns:
            Hex HMAC-SHA256.
        """
        return hmac.new(config.AUTH_SECRET.encode(), f"{address}:{code}".encode(), hashlib.sha256).hexdigest()

    def request_code(self, db: Session, email: str, ip: str | None = None) -> None:
        """Generates a login code and emails it, invalidating any earlier
        outstanding code for the address.

        The DB write is committed *before* the email is sent, so no
        transaction (and, on SQLite, no write lock) is held open across a
        slow SMTP call.

        Args:
            db: Session to write through; committed here.
            email: Address as typed (normalized here).
            ip: Requesting client's IP for per-IP rate limiting, if known.

        Raises:
            AuthError: `"invalid_email"`, `"rate_limited"` (too many
                requests for this address or IP in the last hour), or
                `"email_delivery_failed"`.
        """
        address = normalize_email(email)
        now = _now()
        db.execute(
            delete(LoginCode)
            .where(LoginCode.expires_at < now - _PURGE_AFTER)
            .execution_options(synchronize_session="fetch")
        )

        hour_ago = now - timedelta(hours=1)
        recent_for_email = db.scalar(
            select(func.count()).select_from(LoginCode).where(LoginCode.email == address, LoginCode.created_at > hour_ago)
        )
        if recent_for_email >= config.LOGIN_CODE_MAX_REQUESTS_PER_EMAIL_HOUR:
            db.commit()
            raise AuthError("rate_limited")
        if ip:
            recent_for_ip = db.scalar(
                select(func.count()).select_from(LoginCode).where(LoginCode.request_ip == ip, LoginCode.created_at > hour_ago)
            )
            if recent_for_ip >= config.LOGIN_CODE_MAX_REQUESTS_PER_IP_HOUR:
                db.commit()
                raise AuthError("rate_limited")

        db.execute(
            update(LoginCode).where(LoginCode.email == address, LoginCode.consumed_at.is_(None)).values(consumed_at=now)
        )
        code = f"{secrets.randbelow(10**_CODE_LENGTH):0{_CODE_LENGTH}d}"
        row = LoginCode(
            email=address,
            code_hash=self._hash_code(address, code),
            created_at=now,
            expires_at=now + timedelta(minutes=config.LOGIN_CODE_TTL_MINUTES),
            request_ip=ip,
        )
        db.add(row)
        db.commit()

        try:
            self._sender().send_login_code(address, code, config.LOGIN_CODE_TTL_MINUTES)
        except EmailDeliveryError as exc:
            # The code never reached the user - burn it. It still counts
            # toward the rate limit, which is the honest outcome for a
            # request that consumed a send attempt.
            row.consumed_at = _now()
            db.commit()
            raise AuthError("email_delivery_failed", str(exc)) from exc

    def verify_code(self, db: Session, email: str, code: str) -> UserRead:
        """Checks `code` against the address's newest outstanding code and,
        if it matches, returns the user - creating the account if this is
        the address's first login. Also promotes the address to admin if
        it is listed in `ADMIN_EMAILS`.

        Args:
            db: Session to read/write through; committed here.
            email: Address the code was requested for (normalized here).
            code: What the user typed (whitespace around it is ignored).

        Returns:
            The authenticated user.

        Raises:
            AuthError: `"invalid_email"`; `"invalid_code"` (wrong, expired,
                already used, or none requested); `"too_many_attempts"`
                (this wrong guess was the last allowed one - the code is
                now burned and a new one has to be requested);
                `"account_disabled"`.
        """
        address = normalize_email(email)
        entered = code.strip()
        now = _now()

        row = db.scalars(
            select(LoginCode)
            .where(LoginCode.email == address, LoginCode.consumed_at.is_(None), LoginCode.expires_at > now)
            .order_by(LoginCode.created_at.desc(), LoginCode.id.desc())
            .limit(1)
        ).first()
        if row is None:
            raise AuthError("invalid_code")

        row.attempts += 1
        matches = (
            len(entered) == _CODE_LENGTH
            and entered.isascii()
            and entered.isdigit()
            and hmac.compare_digest(self._hash_code(address, entered), row.code_hash)
        )
        if not matches:
            burned = row.attempts >= config.LOGIN_CODE_MAX_ATTEMPTS
            if burned:
                row.consumed_at = now
            db.commit()
            raise AuthError("too_many_attempts" if burned else "invalid_code")

        row.consumed_at = now
        user = db.scalar(select(User).where(User.email == address))
        if user is None:
            # is_active set explicitly: the column's Python-side default only
            # applies at flush, so it would still be None for the check below.
            user = User(email=address, is_admin=address in config.ADMIN_EMAILS, is_active=True, created_at=now)
            db.add(user)
        elif address in config.ADMIN_EMAILS and not user.is_admin:
            user.is_admin = True
        if not user.is_active:
            db.commit()
            raise AuthError("account_disabled")
        user.last_login_at = now
        db.commit()
        return UserRead.model_validate(user)

    @staticmethod
    def get_active_user(db: Session, user_id: int) -> UserRead | None:
        """Loads the user a session claims to be, so deactivating or
        demoting an account takes effect on the next page load rather than
        whenever the cookie expires.

        Args:
            db: Session to read through.
            user_id: `users.id` stored in the session.

        Returns:
            The user, or `None` if the id is unknown or the account is
            deactivated.
        """
        user = db.get(User, user_id)
        if user is None or not user.is_active:
            return None
        return UserRead.model_validate(user)


# Shared instance the UI layer uses (app/ui/auth.py). Stateless apart from
# the lazily built email sender, so unlike the conversation orchestrator
# there's nothing here that has to be shared across requests.
auth_service = AuthService()

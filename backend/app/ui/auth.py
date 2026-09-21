"""Login state for one browser connection: who is logged in, and the
request-code / verify-code / logout actions the login dialog drives.

A login is just two keys in NiceGUI's `app.storage.user` (the server-side
per-browser store behind the signed session cookie - see
`NICEGUI_STORAGE_SECRET` in `app/core/config.py`): the user id and when it
was issued. Nothing else about the user is cached there. `refresh()`
re-reads the user from the DB on every page load, so deactivating or
demoting an account takes effect on the next load, and a session older than
`AUTH_SESSION_DAYS` is dropped server-side no matter what the cookie says.

Who may do what is decided from `AuthState` (`is_admin`), never from what
the page happens to render: hiding a button is cosmetic, since a browser
can send any event over the websocket to any element that exists on its
page. Admin-only pages therefore refuse to build the privileged elements at
all for non-admins (see `app/ui/admin.py`), and handlers that don't have
that option re-check (see `app/ui/components/api_key_dialog.py`).
"""

import logging
import time
from dataclasses import dataclass

from nicegui import app, run, ui

from app.core import config
from app.schemas.auth import UserRead
from app.services.auth import AuthError, auth_service
from app.ui import db as ui_db

logger = logging.getLogger(__name__)

USER_ID_KEY = "auth_user_id"
ISSUED_AT_KEY = "auth_issued_at"


def _client_ip() -> str | None:
    """The requesting client's IP, for per-IP rate limiting of code
    requests. Behind a reverse proxy this is the proxy's address unless
    uvicorn trusts its forwarded headers (`--forwarded-allow-ips`), in
    which case it is the real client's.

    Returns:
        The address, or `None` if the client has no request attached.
    """
    try:
        client = ui.context.client.request.client
    except RuntimeError:
        return None
    return client.host if client else None


@dataclass
class AuthState:
    """Who is logged in on this browser connection. Built once per page
    load (see `app/ui/pages.py`), so - like `ConversationState` - plain
    instance state is already per-connection.
    """

    user: UserRead | None = None

    @property
    def is_logged_in(self) -> bool:
        """True if a user is logged in."""
        return self.user is not None

    @property
    def is_admin(self) -> bool:
        """True if the logged-in user has admin rights."""
        return self.user is not None and self.user.is_admin

    async def refresh(self) -> None:
        """Loads the user the session claims to be, dropping the session
        if it has expired or the account no longer exists / is disabled.
        A DB failure leaves the user logged out for this page load but
        keeps the session, so a transient error doesn't log anyone out for
        good.
        """
        user_id = app.storage.user.get(USER_ID_KEY)
        if user_id is None:
            self.user = None
            return

        issued_at = app.storage.user.get(ISSUED_AT_KEY)
        session_ttl_seconds = config.AUTH_SESSION_DAYS * 86400
        if not isinstance(issued_at, (int, float)) or time.time() - issued_at > session_ttl_seconds:
            self._forget()
            return

        def _load() -> UserRead | None:
            with ui_db.get_session() as db:
                return auth_service.get_active_user(db, user_id)

        try:
            self.user = await run.io_bound(_load)
        except Exception:
            logger.exception("Loading the logged-in user failed")
            self.user = None
            return
        if self.user is None:
            self._forget()

    async def request_code(self, email: str) -> str | None:
        """Emails a login code to `email`.

        Args:
            email: Address as typed.

        Returns:
            `None` on success, else an error code that
            `STRINGS["auth"]["errors"]` has text for: an
            `AuthError.code`, `"email_not_configured"` (the selected
            `EMAIL_BACKEND` is misconfigured) or `"unknown_error"`.
        """
        ip = _client_ip()

        def _request() -> None:
            with ui_db.get_session() as db:
                auth_service.request_code(db, email, ip)

        try:
            await run.io_bound(_request)
        except AuthError as exc:
            if exc.code == "email_delivery_failed":
                logger.warning("Login code delivery failed: %s", exc, exc_info=exc.__cause__)
            return exc.code
        except RuntimeError:
            logger.exception("Requesting a login code raised RuntimeError - EMAIL_BACKEND misconfigured?")
            return "email_not_configured"
        except Exception:
            logger.exception("Requesting a login code failed")
            return "unknown_error"
        return None

    async def verify_code(self, email: str, code: str) -> str | None:
        """Checks the code and, on success, starts the session.

        Args:
            email: Address the code was sent to.
            code: What the user typed.

        Returns:
            `None` on success (`self.user` is now set), else an error code
            as for `request_code`.
        """

        def _verify() -> UserRead:
            with ui_db.get_session() as db:
                return auth_service.verify_code(db, email, code)

        try:
            user = await run.io_bound(_verify)
        except AuthError as exc:
            return exc.code
        except Exception:
            logger.exception("Verifying a login code failed")
            return "unknown_error"

        app.storage.user[USER_ID_KEY] = user.id
        app.storage.user[ISSUED_AT_KEY] = time.time()
        self.user = user
        return None

    def logout(self) -> None:
        """Ends the session. Leaves the rest of `app.storage.user` alone
        (e.g. the custom car order is a browser preference, not part of
        the login).
        """
        self._forget()
        self.user = None

    @staticmethod
    def _forget() -> None:
        app.storage.user.pop(USER_ID_KEY, None)
        app.storage.user.pop(ISSUED_AT_KEY, None)

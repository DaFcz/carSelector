"""Outgoing email for login codes. One small interface, two backends:
`ConsoleEmailSender` (default - prints to the server log, dev only) and
`SmtpEmailSender` (stdlib `smtplib`, no extra dependency). Which one is
used is `EMAIL_BACKEND` in `app/core/config.py`.

Sending is synchronous and can take seconds (or fail), so callers in the UI
layer run it through `nicegui.run.io_bound` - see `app/ui/auth.py`.
"""

import logging
import smtplib
import ssl
from abc import ABC, abstractmethod
from email.message import EmailMessage

from app.core import config

logger = logging.getLogger(__name__)

LOGIN_CODE_SUBJECT = "Váš přihlašovací kód do Rovis"


class EmailDeliveryError(Exception):
    """The mail could not be handed to the mail server. The underlying
    cause is chained (`__cause__`) for logs; it is never shown to users.
    """


def login_code_body(code: str, ttl_minutes: int) -> str:
    """Builds the plain-text body of the login-code email (Czech, like all
    user-facing text - see doc/prompt/CLAUDE.md).

    Args:
        code: The one-time code to show.
        ttl_minutes: How long the code stays valid, quoted in the text.

    Returns:
        The message body.
    """
    return (
        f"Váš přihlašovací kód: {code}\n\n"
        f"Kód platí {ttl_minutes} minut a jde použít jen jednou.\n"
        "Pokud jste se nepřihlašovali, tento e-mail můžete ignorovat.\n"
    )


class EmailSender(ABC):
    """Delivers a login code to an address."""

    @abstractmethod
    def send_login_code(self, to_address: str, code: str, ttl_minutes: int) -> None:
        """Sends `code` to `to_address`.

        Args:
            to_address: Recipient (already normalized/validated).
            code: The plaintext one-time code - the only place besides the
                user's inbox it ever exists (the DB stores just a hash).
            ttl_minutes: Validity, quoted in the message.

        Raises:
            EmailDeliveryError: The message could not be sent.
        """


class ConsoleEmailSender(EmailSender):
    """Development backend: logs the code instead of sending anything, so
    the login flow works locally with no mail server. Never use in
    production - anyone with log access could read every login code.
    """

    def send_login_code(self, to_address: str, code: str, ttl_minutes: int) -> None:
        """Logs the code at WARNING level (visible under uvicorn's default
        logging config, which would hide INFO from app loggers).

        Args:
            to_address: Recipient the code is for.
            code: The one-time code.
            ttl_minutes: Unused here; kept for interface parity.
        """
        logger.warning("LOGIN CODE for %s: %s  (EMAIL_BACKEND=console - development only)", to_address, code)


class SmtpEmailSender(EmailSender):
    """Sends through an SMTP server configured by `SMTP_*` in
    `app/core/config.py`.
    """

    def __init__(
        self,
        host: str,
        port: int,
        username: str | None,
        password: str | None,
        from_address: str,
        security: str = "starttls",
    ) -> None:
        """Args:
            host: SMTP server hostname.
            port: SMTP port (587 for `starttls`, 465 for `ssl`).
            username: Login name, or `None` for an unauthenticated relay.
            password: Login password, or `None`.
            from_address: Sender address for the `From` header/envelope.
            security: `"starttls"`, `"ssl"` (implicit TLS) or `"none"`.
        """
        self._host = host
        self._port = port
        self._username = username
        self._password = password
        self._from_address = from_address
        self._security = security

    def send_login_code(self, to_address: str, code: str, ttl_minutes: int) -> None:
        """Sends the login-code email.

        Args:
            to_address: Recipient.
            code: The one-time code.
            ttl_minutes: Validity, quoted in the message.

        Raises:
            EmailDeliveryError: Connection, TLS, authentication or
                recipient failure - anything `smtplib`/`OSError` raises.
        """
        message = EmailMessage()
        message["Subject"] = LOGIN_CODE_SUBJECT
        message["From"] = self._from_address
        message["To"] = to_address
        message.set_content(login_code_body(code, ttl_minutes))

        try:
            if self._security == "ssl":
                smtp: smtplib.SMTP = smtplib.SMTP_SSL(
                    self._host, self._port, timeout=15, context=ssl.create_default_context()
                )
            else:
                smtp = smtplib.SMTP(self._host, self._port, timeout=15)
            with smtp:
                if self._security == "starttls":
                    smtp.starttls(context=ssl.create_default_context())
                if self._username:
                    smtp.login(self._username, self._password or "")
                smtp.send_message(message)
        except (smtplib.SMTPException, OSError) as exc:
            raise EmailDeliveryError(f"SMTP delivery to {self._host}:{self._port} failed") from exc


def get_email_sender() -> EmailSender:
    """Builds the sender `EMAIL_BACKEND` selects.

    Returns:
        A `SmtpEmailSender` for `"smtp"`, a `ConsoleEmailSender` for
        `"console"`.

    Raises:
        RuntimeError: `EMAIL_BACKEND` is unknown, or is `"smtp"` without
            `SMTP_HOST`/`SMTP_FROM` (or `SMTP_USER`) - fails loudly rather
            than silently never delivering codes, same policy as
            `app/ai/client.py` for a missing API key.
    """
    if config.EMAIL_BACKEND == "console":
        logger.warning("EMAIL_BACKEND=console: login codes are printed to the log, not emailed (development only)")
        return ConsoleEmailSender()
    if config.EMAIL_BACKEND == "smtp":
        if not config.SMTP_HOST or not config.SMTP_FROM:
            raise RuntimeError("EMAIL_BACKEND=smtp requires SMTP_HOST and SMTP_FROM (or SMTP_USER) to be set")
        return SmtpEmailSender(
            config.SMTP_HOST,
            config.SMTP_PORT,
            config.SMTP_USER,
            config.SMTP_PASSWORD,
            config.SMTP_FROM,
            config.SMTP_SECURITY,
        )
    raise RuntimeError(f"Unknown EMAIL_BACKEND {config.EMAIL_BACKEND!r} - expected 'console' or 'smtp'")

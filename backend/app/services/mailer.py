"""Outgoing email for login codes. One small interface, two backends:
`ConsoleEmailSender` (default - prints to the server log, dev only) and
`SmtpEmailSender` (stdlib `smtplib`, no extra dependency). Which one is
used is `EMAIL_BACKEND` in `app/core/config.py`.

Sending is synchronous and can take seconds (or fail), so callers in the UI
layer run it through `nicegui.run.io_bound` - see `app/ui/auth.py`.

Any SMTP account works (Seznam, Gmail with an app password, Brevo, Mailgun,
Resend, your own server, ...): only host, port, credentials and the TLS mode
differ - see `backend/README.md`'s Login section. `scripts/send_test_email.py`
sends one message through the configured backend, to check a setup without
going through the login flow.

Deliverability is mostly not code: mail from a domain you own also needs SPF
and DKIM records for it (your provider tells you which), or receivers will
file the codes under spam. Providers like Seznam and Gmail only accept their
own account address as the sender, which is why `SMTP_FROM` defaults to
`SMTP_USER`.
"""

import html
import logging
import smtplib
import ssl
from abc import ABC, abstractmethod
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid

import certifi

from app.core import config

logger = logging.getLogger(__name__)

LOGIN_CODE_SUBJECT = "Váš přihlašovací kód do Rovis"
SMTP_TIMEOUT_SECONDS = 15
_SECURITY_MODES = ("starttls", "ssl", "none")


def _default_ssl_context() -> ssl.SSLContext:
    """Builds the TLS context used when a sender isn't given one explicitly.

    Trusts certifi's CA bundle instead of `ssl.create_default_context()`'s
    own default (the OS trust store). On Windows that default is the
    system's Certificate Store, which isn't guaranteed to have picked up a
    newly issued CA - certifi is a pinned, regularly updated dependency, so
    behavior doesn't depend on how current a given machine's OS store is.
    Certificate and hostname verification stay fully on either way.
    """
    return ssl.create_default_context(cafile=certifi.where())


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


def login_code_html(code: str, ttl_minutes: int) -> str:
    """Builds the HTML alternative of the login-code email: the same text,
    with the code large enough to read at a glance. Inline styles only -
    mail clients strip `<style>` blocks.

    Args:
        code: The one-time code to show.
        ttl_minutes: How long the code stays valid, quoted in the text.

    Returns:
        A small self-contained HTML document.
    """
    return (
        '<!doctype html><html lang="cs"><body style="font-family:Arial,Helvetica,sans-serif;color:#222">'
        "<p>Váš přihlašovací kód:</p>"
        f'<p style="font-size:30px;font-weight:bold;letter-spacing:6px;margin:8px 0">{html.escape(code)}</p>'
        f"<p>Kód platí {int(ttl_minutes)} minut a jde použít jen jednou.</p>"
        '<p style="color:#666;font-size:13px">Pokud jste se nepřihlašovali, tento e-mail můžete ignorovat.</p>'
        "</body></html>"
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
        from_name: str | None = None,
        ssl_context: ssl.SSLContext | None = None,
    ) -> None:
        """Args:
            host: SMTP server hostname.
            port: SMTP port (587 for `starttls`, 465 for `ssl`).
            username: Login name, or `None` for an unauthenticated relay.
                Most providers want the full email address.
            password: Login password (or app password), or `None`.
            from_address: Sender address for the `From` header/envelope.
            security: `"starttls"`, `"ssl"` (implicit TLS) or `"none"`.
            from_name: Display name shown next to the sender address.
            ssl_context: TLS settings. Defaults to the system trust store
                with certificate and hostname verification on; overridden
                only in tests (to trust a throwaway self-signed cert) -
                verification is never turned off in production code.
        """
        self._host = host
        self._port = port
        self._username = username
        self._password = password
        self._from_address = from_address
        self._security = security
        self._from_name = from_name
        self._ssl_context = ssl_context

    def _build_message(self, to_address: str, code: str, ttl_minutes: int) -> EmailMessage:
        """Builds the login-code message: plain text plus an HTML
        alternative, with the `Date` and `Message-ID` headers that
        `smtplib` does not add itself and spam filters look for.

        Args:
            to_address: Recipient.
            code: The one-time code.
            ttl_minutes: Validity, quoted in the message.

        Returns:
            The ready-to-send message.
        """
        message = EmailMessage()
        message["Subject"] = LOGIN_CODE_SUBJECT
        message["From"] = formataddr((self._from_name, self._from_address)) if self._from_name else self._from_address
        message["To"] = to_address
        message["Date"] = formatdate(localtime=False)
        message["Message-ID"] = make_msgid(domain=self._from_address.rpartition("@")[2] or None)
        # Tells auto-responders (out-of-office etc.) not to answer a mail
        # nobody is reading.
        message["Auto-Submitted"] = "auto-generated"
        message.set_content(login_code_body(code, ttl_minutes))
        message.add_alternative(login_code_html(code, ttl_minutes), subtype="html")
        return message

    def send_login_code(self, to_address: str, code: str, ttl_minutes: int) -> None:
        """Sends the login-code email.

        Args:
            to_address: Recipient.
            code: The one-time code.
            ttl_minutes: Validity, quoted in the message.

        Raises:
            EmailDeliveryError: Connection, TLS (including a certificate
                that fails verification), authentication or recipient
                failure - anything `smtplib`/`ssl`/`OSError` raises. The
                message names the failure (never the code or password).
        """
        message = self._build_message(to_address, code, ttl_minutes)
        context = self._ssl_context or _default_ssl_context()

        try:
            if self._security == "ssl":
                smtp: smtplib.SMTP = smtplib.SMTP_SSL(self._host, self._port, timeout=SMTP_TIMEOUT_SECONDS, context=context)
            else:
                smtp = smtplib.SMTP(self._host, self._port, timeout=SMTP_TIMEOUT_SECONDS)
            with smtp:
                if self._security == "starttls":
                    smtp.starttls(context=context)
                if self._username:
                    smtp.login(self._username, self._password or "")
                smtp.send_message(message, from_addr=self._from_address, to_addrs=[to_address])
        except (smtplib.SMTPException, ssl.SSLError, OSError) as exc:
            raise EmailDeliveryError(
                f"SMTP delivery via {self._host}:{self._port} ({self._security}) failed: {type(exc).__name__}: {exc}"
            ) from exc


def get_email_sender() -> EmailSender:
    """Builds the sender `EMAIL_BACKEND` selects.

    Returns:
        A `SmtpEmailSender` for `"smtp"`, a `ConsoleEmailSender` for
        `"console"`.

    Raises:
        RuntimeError: `EMAIL_BACKEND` is unknown, or is `"smtp"` with
            missing/invalid settings - fails loudly rather than silently
            never delivering codes, same policy as `app/ai/client.py` for a
            missing API key.
    """
    if config.EMAIL_BACKEND == "console":
        logger.warning("EMAIL_BACKEND=console: login codes are printed to the log, not emailed (development only)")
        return ConsoleEmailSender()
    if config.EMAIL_BACKEND == "smtp":
        problem = smtp_config_problem()
        if problem:
            raise RuntimeError(problem)
        return SmtpEmailSender(
            config.SMTP_HOST,
            config.SMTP_PORT,
            config.SMTP_USER,
            config.SMTP_PASSWORD,
            config.SMTP_FROM,
            config.SMTP_SECURITY,
            config.SMTP_FROM_NAME,
        )
    raise RuntimeError(f"Unknown EMAIL_BACKEND {config.EMAIL_BACKEND!r} - expected 'console' or 'smtp'")


def smtp_config_problem() -> str | None:
    """Checks the `SMTP_*` settings without connecting anywhere.

    Returns:
        A description of what is wrong, or `None` if the settings are
        complete and consistent.
    """
    if not config.SMTP_HOST:
        return "EMAIL_BACKEND=smtp requires SMTP_HOST to be set"
    if not config.SMTP_FROM:
        return "EMAIL_BACKEND=smtp requires SMTP_FROM (or SMTP_USER, which it defaults to) to be set"
    if "@" not in config.SMTP_FROM:
        return f"SMTP_FROM must be an email address, got {config.SMTP_FROM!r}"
    if config.SMTP_SECURITY not in _SECURITY_MODES:
        return f"SMTP_SECURITY must be one of {', '.join(_SECURITY_MODES)}, got {config.SMTP_SECURITY!r}"
    if config.SMTP_USER and not config.SMTP_PASSWORD:
        return "SMTP_USER is set but SMTP_PASSWORD is empty"
    return None


def log_email_backend_status() -> None:
    """Logs, once at startup, how login codes will be delivered - so a
    forgotten `EMAIL_BACKEND` shows up when the server starts, not when the
    first person waits for a mail that never comes. Never raises: a broken
    mail setup must not stop the catalog and chat from running, and the
    login dialog reports it (`email_not_configured`) when someone tries.
    """
    if config.EMAIL_BACKEND == "console":
        logger.warning(
            "EMAIL_BACKEND=console: login codes are NOT emailed, they are printed here in the log. "
            "Set EMAIL_BACKEND=smtp and SMTP_* to send real mail (see backend/README.md)."
        )
    elif config.EMAIL_BACKEND == "smtp":
        problem = smtp_config_problem()
        if problem:
            logger.error("Email login is broken: %s", problem)
            return
        logger.info(
            "Login codes are sent via SMTP %s:%s (%s) from %s",
            config.SMTP_HOST,
            config.SMTP_PORT,
            config.SMTP_SECURITY,
            config.SMTP_FROM,
        )
        if config.SMTP_SECURITY == "none" and config.SMTP_USER:
            logger.warning("SMTP_SECURITY=none: the SMTP password is sent unencrypted")
    else:
        logger.error("Email login is broken: unknown EMAIL_BACKEND %r (expected 'console' or 'smtp')", config.EMAIL_BACKEND)

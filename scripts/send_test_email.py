#!/usr/bin/env python3
"""Sends one login-code-style email through the configured backend, to check
the SMTP setup without going through the login dialog (and without needing a
database).

    python scripts/send_test_email.py you@example.cz

Reads the same settings the app does (`EMAIL_BACKEND`, `SMTP_*`, from the
environment or backend/.env - see backend/README.md's Login section). The
message carries the placeholder code 123456, which is not a valid login code.
Exits 0 if the mail server accepted the message, 1 otherwise; "accepted"
means handed over, not delivered - if nothing arrives, look in the spam
folder and at your provider's sending log (see the deliverability note in
app/services/mailer.py).
"""

import argparse
import smtplib
import ssl
import sys
from pathlib import Path

# backend/ isn't on sys.path when run from the repo root - same fix
# scripts/import_scraper_data.py applies for its own imports.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.core import config  # noqa: E402
from app.services.auth import AuthError, normalize_email  # noqa: E402
from app.services.mailer import EmailDeliveryError, get_email_sender, smtp_config_problem  # noqa: E402

PLACEHOLDER_CODE = "123456"


def hint_for(cause: BaseException | None) -> str | None:
    """Maps the most common SMTP failures to what usually fixes them.

    Args:
        cause: The exception `EmailDeliveryError` was raised from.

    Returns:
        A one-line suggestion, or `None` if there is nothing specific to say.
    """
    if isinstance(cause, smtplib.SMTPAuthenticationError):
        return (
            "The server rejected SMTP_USER/SMTP_PASSWORD. Use the full email address as the user; "
            "Gmail and some others require an app password rather than the normal account password."
        )
    if isinstance(cause, smtplib.SMTPSenderRefused):
        return "The server refused the sender. Most providers only accept their own account address as SMTP_FROM."
    if isinstance(cause, ssl.SSLCertVerificationError):
        return "The server's TLS certificate failed verification - check SMTP_HOST matches the certificate's name."
    if isinstance(cause, ssl.SSLError):
        return "TLS handshake failed - the port and SMTP_SECURITY probably don't match (587 = starttls, 465 = ssl)."
    if isinstance(cause, (TimeoutError, ConnectionError, OSError)):
        return "Could not reach the server - check SMTP_HOST, SMTP_PORT and any firewall/VPN blocking outbound SMTP."
    return None


def main() -> int:
    """Runs the check.

    Returns:
        The process exit code.
    """
    parser = argparse.ArgumentParser(description="Send a test login-code email through the configured backend.")
    parser.add_argument("to", help="Recipient address")
    args = parser.parse_args()

    try:
        recipient = normalize_email(args.to)
    except AuthError:
        print(f"'{args.to}' is not a valid email address.")
        return 1

    print(f"EMAIL_BACKEND={config.EMAIL_BACKEND}")
    if config.EMAIL_BACKEND == "smtp":
        problem = smtp_config_problem()
        if problem:
            print(f"Configuration problem: {problem}")
            return 1
        print(f"SMTP {config.SMTP_HOST}:{config.SMTP_PORT} ({config.SMTP_SECURITY}), user {config.SMTP_USER or '(none)'}, from {config.SMTP_FROM}")

    try:
        sender = get_email_sender()
        sender.send_login_code(recipient, PLACEHOLDER_CODE, config.LOGIN_CODE_TTL_MINUTES)
    except RuntimeError as exc:
        print(f"Configuration problem: {exc}")
        return 1
    except EmailDeliveryError as exc:
        print(f"FAILED: {exc}")
        hint = hint_for(exc.__cause__)
        if hint:
            print(f"Hint: {hint}")
        return 1

    if config.EMAIL_BACKEND == "console":
        print("Console backend: nothing was sent (the code above went to the log). Set EMAIL_BACKEND=smtp to send real mail.")
        return 0
    print(f"OK: the mail server accepted the message for {recipient}. Check the inbox (and spam folder).")
    return 0


if __name__ == "__main__":
    sys.exit(main())

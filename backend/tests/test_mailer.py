import logging

import pytest

from app.core import config
from app.services import mailer
from app.services.mailer import (
    ConsoleEmailSender,
    EmailDeliveryError,
    SmtpEmailSender,
    get_email_sender,
    login_code_body,
)


class FakeSmtp:
    """Stands in for smtplib.SMTP / SMTP_SSL and records what happened."""

    instances: list["FakeSmtp"] = []
    fail_on_send = False

    def __init__(self, host: str, port: int, **kwargs: object) -> None:
        self.host, self.port, self.kwargs = host, port, kwargs
        self.calls: list[str] = []
        self.message = None
        FakeSmtp.instances.append(self)

    def __enter__(self) -> "FakeSmtp":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.calls.append("quit")

    def starttls(self, **kwargs: object) -> None:
        self.calls.append("starttls")

    def login(self, username: str, password: str) -> None:
        self.calls.append(f"login:{username}:{password}")

    def send_message(self, message: object) -> None:
        if FakeSmtp.fail_on_send:
            raise mailer.smtplib.SMTPRecipientsRefused({})
        self.calls.append("send")
        self.message = message


@pytest.fixture(autouse=True)
def fake_smtp(monkeypatch: pytest.MonkeyPatch) -> type[FakeSmtp]:
    FakeSmtp.instances = []
    FakeSmtp.fail_on_send = False
    monkeypatch.setattr(mailer.smtplib, "SMTP", FakeSmtp)
    monkeypatch.setattr(mailer.smtplib, "SMTP_SSL", FakeSmtp)
    return FakeSmtp


def test_login_code_body_contains_code_and_validity() -> None:
    body = login_code_body("123456", 10)
    assert "123456" in body
    assert "10 minut" in body


def test_console_sender_logs_the_code(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING):
        ConsoleEmailSender().send_login_code("jana@example.cz", "123456", 10)
    assert "123456" in caplog.text
    assert "jana@example.cz" in caplog.text


def test_smtp_sender_uses_starttls_login_and_sends_the_code(fake_smtp: type[FakeSmtp]) -> None:
    sender = SmtpEmailSender("smtp.example.cz", 587, "user", "secret", "no-reply@example.cz", "starttls")
    sender.send_login_code("jana@example.cz", "123456", 10)

    (smtp,) = fake_smtp.instances
    assert (smtp.host, smtp.port) == ("smtp.example.cz", 587)
    assert smtp.calls == ["starttls", "login:user:secret", "send", "quit"]
    assert smtp.message["To"] == "jana@example.cz"
    assert smtp.message["From"] == "no-reply@example.cz"
    assert "123456" in smtp.message.get_content()


def test_smtp_sender_without_credentials_skips_login(fake_smtp: type[FakeSmtp]) -> None:
    SmtpEmailSender("relay.local", 25, None, None, "no-reply@example.cz", "none").send_login_code(
        "jana@example.cz", "123456", 10
    )
    assert fake_smtp.instances[0].calls == ["send", "quit"]


def test_smtp_sender_wraps_failures(fake_smtp: type[FakeSmtp]) -> None:
    fake_smtp.fail_on_send = True
    sender = SmtpEmailSender("smtp.example.cz", 587, "user", "secret", "no-reply@example.cz")
    with pytest.raises(EmailDeliveryError):
        sender.send_login_code("jana@example.cz", "123456", 10)


def test_smtp_sender_wraps_connection_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    def _refuse(*_args: object, **_kwargs: object) -> None:
        raise ConnectionRefusedError("nope")

    monkeypatch.setattr(mailer.smtplib, "SMTP", _refuse)
    sender = SmtpEmailSender("smtp.example.cz", 587, None, None, "no-reply@example.cz", "none")
    with pytest.raises(EmailDeliveryError):
        sender.send_login_code("jana@example.cz", "123456", 10)


def test_get_email_sender_selects_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "EMAIL_BACKEND", "console")
    assert isinstance(get_email_sender(), ConsoleEmailSender)

    monkeypatch.setattr(config, "EMAIL_BACKEND", "smtp")
    monkeypatch.setattr(config, "SMTP_HOST", "smtp.example.cz")
    monkeypatch.setattr(config, "SMTP_FROM", "no-reply@example.cz")
    assert isinstance(get_email_sender(), SmtpEmailSender)


def test_smtp_backend_without_host_fails_loudly(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "EMAIL_BACKEND", "smtp")
    monkeypatch.setattr(config, "SMTP_HOST", None)
    with pytest.raises(RuntimeError, match="SMTP_HOST"):
        get_email_sender()


def test_unknown_backend_fails_loudly(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "EMAIL_BACKEND", "carrier-pigeon")
    with pytest.raises(RuntimeError, match="carrier-pigeon"):
        get_email_sender()

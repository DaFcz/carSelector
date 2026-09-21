"""Backend selection, configuration checks, startup logging and the message
templates. Actual SMTP behaviour (TLS, auth, message format on the wire) is
covered against a real socket in test_smtp_wire.py.
"""

import importlib
import logging

import pytest

from app.core import config
from app.services.auth import AuthError, normalize_email
from app.services.mailer import (
    ConsoleEmailSender,
    SmtpEmailSender,
    get_email_sender,
    log_email_backend_status,
    login_code_body,
    login_code_html,
    smtp_config_problem,
)


@pytest.fixture()
def valid_smtp_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "EMAIL_BACKEND", "smtp")
    monkeypatch.setattr(config, "SMTP_HOST", "smtp.example.cz")
    monkeypatch.setattr(config, "SMTP_PORT", 587)
    monkeypatch.setattr(config, "SMTP_USER", "no-reply@example.cz")
    monkeypatch.setattr(config, "SMTP_PASSWORD", "pw")
    monkeypatch.setattr(config, "SMTP_FROM", "no-reply@example.cz")
    monkeypatch.setattr(config, "SMTP_SECURITY", "starttls")


def test_login_code_body_contains_code_and_validity() -> None:
    body = login_code_body("123456", 10)
    assert "123456" in body
    assert "10 minut" in body


def test_login_code_html_contains_code_and_validity() -> None:
    body = login_code_html("123456", 10)
    assert "123456" in body
    assert "10 minut" in body


def test_login_code_html_escapes_its_input() -> None:
    assert "<script>" not in login_code_html("<script>alert(1)</script>", 10)


def test_console_sender_logs_the_code(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING):
        ConsoleEmailSender().send_login_code("jana@example.cz", "123456", 10)
    assert "123456" in caplog.text
    assert "jana@example.cz" in caplog.text


def test_get_email_sender_selects_backend(monkeypatch: pytest.MonkeyPatch, valid_smtp_config: None) -> None:
    assert isinstance(get_email_sender(), SmtpEmailSender)

    monkeypatch.setattr(config, "EMAIL_BACKEND", "console")
    assert isinstance(get_email_sender(), ConsoleEmailSender)


def test_unknown_backend_fails_loudly(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "EMAIL_BACKEND", "carrier-pigeon")
    with pytest.raises(RuntimeError, match="carrier-pigeon"):
        get_email_sender()


def test_valid_smtp_config_has_no_problem(valid_smtp_config: None) -> None:
    assert smtp_config_problem() is None


@pytest.mark.parametrize(
    ("setting", "value", "expected"),
    [
        ("SMTP_HOST", None, "SMTP_HOST"),
        ("SMTP_FROM", None, "SMTP_FROM"),
        ("SMTP_FROM", "not-an-address", "email address"),
        ("SMTP_SECURITY", "tls1.3", "SMTP_SECURITY"),
        ("SMTP_PASSWORD", "", "SMTP_PASSWORD"),
    ],
)
def test_smtp_config_problems_are_named(
    monkeypatch: pytest.MonkeyPatch, valid_smtp_config: None, setting: str, value: object, expected: str
) -> None:
    monkeypatch.setattr(config, setting, value)

    assert expected in smtp_config_problem()
    with pytest.raises(RuntimeError, match=expected):
        get_email_sender()


def test_startup_status_warns_loudly_about_console_backend(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(config, "EMAIL_BACKEND", "console")
    with caplog.at_level(logging.INFO):
        log_email_backend_status()
    assert "NOT emailed" in caplog.text


def test_startup_status_reports_a_broken_smtp_config_as_an_error(
    monkeypatch: pytest.MonkeyPatch, valid_smtp_config: None, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(config, "SMTP_HOST", None)
    with caplog.at_level(logging.INFO):
        log_email_backend_status()
    assert any(record.levelno == logging.ERROR and "SMTP_HOST" in record.getMessage() for record in caplog.records)


def test_startup_status_for_a_working_smtp_config_names_the_server_but_not_the_password(
    monkeypatch: pytest.MonkeyPatch, valid_smtp_config: None, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(config, "SMTP_PASSWORD", "hunter2-must-never-be-logged")
    with caplog.at_level(logging.DEBUG):
        log_email_backend_status()
    assert "smtp.example.cz" in caplog.text
    assert "hunter2-must-never-be-logged" not in caplog.text


def test_startup_status_warns_when_credentials_would_travel_unencrypted(
    monkeypatch: pytest.MonkeyPatch, valid_smtp_config: None, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(config, "SMTP_SECURITY", "none")
    with caplog.at_level(logging.INFO):
        log_email_backend_status()
    assert "unencrypted" in caplog.text


@pytest.mark.parametrize(("security", "port"), [("starttls", 587), ("ssl", 465), ("none", 25)])
def test_default_smtp_port_follows_the_security_mode(monkeypatch: pytest.MonkeyPatch, security: str, port: int) -> None:
    monkeypatch.setenv("SMTP_SECURITY", security)
    monkeypatch.delenv("SMTP_PORT", raising=False)
    try:
        assert importlib.reload(config).SMTP_PORT == port
        monkeypatch.setenv("SMTP_PORT", "2525")
        assert importlib.reload(config).SMTP_PORT == 2525
        monkeypatch.setenv("SMTP_PORT", "")  # a blank line in .env counts as unset
        assert importlib.reload(config).SMTP_PORT == port
    finally:
        monkeypatch.undo()
        importlib.reload(config)


def test_addresses_cannot_smuggle_extra_headers() -> None:
    """The recipient comes from a text box and ends up in a `To:` header -
    line breaks in it must never get that far."""
    for hostile in ("a@b.cz\r\nBcc: victim@example.cz", "a@b.cz\nBcc: victim@example.cz", "a@b.cz>\r\nX: y"):
        with pytest.raises(AuthError):
            normalize_email(hostile)

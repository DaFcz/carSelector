from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import config
from app.models.login_code import LoginCode
from app.models.user import User
from app.services.auth import AuthError, AuthService, normalize_email
from app.services.mailer import EmailDeliveryError, EmailSender


class RecordingSender(EmailSender):
    """Captures what would have been emailed."""

    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []
        self.fail = False

    def send_login_code(self, to_address: str, code: str, ttl_minutes: int) -> None:
        if self.fail:
            raise EmailDeliveryError("smtp down")
        self.sent.append((to_address, code))

    @property
    def last_code(self) -> str:
        return self.sent[-1][1]


@pytest.fixture()
def sender() -> RecordingSender:
    return RecordingSender()


@pytest.fixture()
def service(sender: RecordingSender) -> AuthService:
    return AuthService(sender)


def _wrong_code(right: str) -> str:
    return "000000" if right != "000000" else "111111"


def test_normalize_email_strips_and_lowercases() -> None:
    assert normalize_email("  Jana.Novak@Example.CZ ") == "jana.novak@example.cz"


@pytest.mark.parametrize("bad", ["", "   ", "no-at-sign", "a@b", "two@@example.cz", "sp ace@example.cz", "a" * 320 + "@x.cz"])
def test_normalize_email_rejects_malformed_addresses(bad: str) -> None:
    with pytest.raises(AuthError) as exc_info:
        normalize_email(bad)
    assert exc_info.value.code == "invalid_email"


def test_request_code_emails_a_six_digit_code_and_stores_only_its_hash(
    db_session: Session, service: AuthService, sender: RecordingSender
) -> None:
    service.request_code(db_session, "Jana@Example.cz")

    assert len(sender.sent) == 1
    to_address, code = sender.sent[0]
    assert to_address == "jana@example.cz"
    assert len(code) == 6 and code.isdigit()

    row = db_session.scalars(select(LoginCode)).one()
    assert row.email == "jana@example.cz"
    assert code not in row.code_hash
    assert row.code_hash == AuthService._hash_code("jana@example.cz", code)


def test_verify_code_creates_account_on_first_login_and_reuses_it_after(
    db_session: Session, service: AuthService, sender: RecordingSender
) -> None:
    service.request_code(db_session, "jana@example.cz")
    first = service.verify_code(db_session, "jana@example.cz", sender.last_code)

    service.request_code(db_session, "JANA@example.cz")
    second = service.verify_code(db_session, "jana@example.cz", sender.last_code)

    assert first.id == second.id
    assert first.email == "jana@example.cz"
    assert first.is_admin is False
    assert db_session.scalars(select(User)).all() == [db_session.get(User, first.id)]
    assert db_session.get(User, first.id).last_login_at is not None


def test_verify_code_tolerates_whitespace_around_the_code(
    db_session: Session, service: AuthService, sender: RecordingSender
) -> None:
    service.request_code(db_session, "jana@example.cz")
    user = service.verify_code(db_session, "jana@example.cz", f"  {sender.last_code}\n")
    assert user.email == "jana@example.cz"


def test_code_is_single_use(db_session: Session, service: AuthService, sender: RecordingSender) -> None:
    service.request_code(db_session, "jana@example.cz")
    code = sender.last_code
    service.verify_code(db_session, "jana@example.cz", code)

    with pytest.raises(AuthError) as exc_info:
        service.verify_code(db_session, "jana@example.cz", code)
    assert exc_info.value.code == "invalid_code"


def test_code_only_works_for_the_address_it_was_issued_to(
    db_session: Session, service: AuthService, sender: RecordingSender
) -> None:
    service.request_code(db_session, "jana@example.cz")
    with pytest.raises(AuthError) as exc_info:
        service.verify_code(db_session, "petr@example.cz", sender.last_code)
    assert exc_info.value.code == "invalid_code"
    assert db_session.scalars(select(User)).all() == []


def test_wrong_code_is_rejected_and_does_not_create_an_account(
    db_session: Session, service: AuthService, sender: RecordingSender
) -> None:
    service.request_code(db_session, "jana@example.cz")
    with pytest.raises(AuthError) as exc_info:
        service.verify_code(db_session, "jana@example.cz", _wrong_code(sender.last_code))
    assert exc_info.value.code == "invalid_code"
    assert db_session.scalars(select(User)).all() == []


@pytest.mark.parametrize("junk", ["", "12345", "1234567", "abcdef", "١٢٣٤٥٦"])
def test_malformed_codes_are_rejected(
    db_session: Session, service: AuthService, sender: RecordingSender, junk: str
) -> None:
    service.request_code(db_session, "jana@example.cz")
    with pytest.raises(AuthError) as exc_info:
        service.verify_code(db_session, "jana@example.cz", junk)
    assert exc_info.value.code == "invalid_code"


def test_code_is_burned_after_max_wrong_attempts_even_if_the_right_one_follows(
    db_session: Session, service: AuthService, sender: RecordingSender
) -> None:
    service.request_code(db_session, "jana@example.cz")
    code = sender.last_code
    wrong = _wrong_code(code)

    for _ in range(config.LOGIN_CODE_MAX_ATTEMPTS - 1):
        with pytest.raises(AuthError) as exc_info:
            service.verify_code(db_session, "jana@example.cz", wrong)
        assert exc_info.value.code == "invalid_code"
    with pytest.raises(AuthError) as exc_info:
        service.verify_code(db_session, "jana@example.cz", wrong)
    assert exc_info.value.code == "too_many_attempts"

    with pytest.raises(AuthError) as exc_info:
        service.verify_code(db_session, "jana@example.cz", code)
    assert exc_info.value.code == "invalid_code"


def test_expired_code_is_rejected(db_session: Session, service: AuthService, sender: RecordingSender) -> None:
    service.request_code(db_session, "jana@example.cz")
    row = db_session.scalars(select(LoginCode)).one()
    row.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db_session.commit()

    with pytest.raises(AuthError) as exc_info:
        service.verify_code(db_session, "jana@example.cz", sender.last_code)
    assert exc_info.value.code == "invalid_code"


def test_requesting_a_new_code_invalidates_the_previous_one(
    db_session: Session, service: AuthService, sender: RecordingSender
) -> None:
    service.request_code(db_session, "jana@example.cz")
    old_code = sender.last_code
    service.request_code(db_session, "jana@example.cz")
    new_code = sender.last_code
    if old_code == new_code:  # 1-in-a-million collision - keep the test deterministic
        pytest.skip("random codes collided")

    with pytest.raises(AuthError):
        service.verify_code(db_session, "jana@example.cz", old_code)
    assert service.verify_code(db_session, "jana@example.cz", new_code).email == "jana@example.cz"


def test_code_requests_are_rate_limited_per_email(
    db_session: Session, service: AuthService, sender: RecordingSender
) -> None:
    for _ in range(config.LOGIN_CODE_MAX_REQUESTS_PER_EMAIL_HOUR):
        service.request_code(db_session, "jana@example.cz")

    with pytest.raises(AuthError) as exc_info:
        service.request_code(db_session, "jana@example.cz")
    assert exc_info.value.code == "rate_limited"
    assert len(sender.sent) == config.LOGIN_CODE_MAX_REQUESTS_PER_EMAIL_HOUR

    service.request_code(db_session, "petr@example.cz")  # other addresses are unaffected


def test_code_requests_are_rate_limited_per_ip(
    db_session: Session, service: AuthService, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(config, "LOGIN_CODE_MAX_REQUESTS_PER_IP_HOUR", 3)
    for index in range(3):
        service.request_code(db_session, f"user{index}@example.cz", ip="203.0.113.7")

    with pytest.raises(AuthError) as exc_info:
        service.request_code(db_session, "another@example.cz", ip="203.0.113.7")
    assert exc_info.value.code == "rate_limited"

    service.request_code(db_session, "another@example.cz", ip="198.51.100.1")


def test_old_codes_stop_counting_toward_the_rate_limit(
    db_session: Session, service: AuthService, sender: RecordingSender
) -> None:
    for _ in range(config.LOGIN_CODE_MAX_REQUESTS_PER_EMAIL_HOUR):
        service.request_code(db_session, "jana@example.cz")
    for row in db_session.scalars(select(LoginCode)):
        row.created_at = datetime.now(timezone.utc) - timedelta(hours=2)
    db_session.commit()

    service.request_code(db_session, "jana@example.cz")


def test_email_delivery_failure_burns_the_code_and_reports_it(
    db_session: Session, service: AuthService, sender: RecordingSender
) -> None:
    sender.fail = True
    with pytest.raises(AuthError) as exc_info:
        service.request_code(db_session, "jana@example.cz")
    assert exc_info.value.code == "email_delivery_failed"
    assert db_session.scalars(select(LoginCode)).one().consumed_at is not None


def test_stale_codes_are_purged_on_the_next_request(
    db_session: Session, service: AuthService, sender: RecordingSender
) -> None:
    service.request_code(db_session, "old@example.cz")
    stale = db_session.scalars(select(LoginCode)).one()
    stale.expires_at = datetime.now(timezone.utc) - timedelta(days=3)
    db_session.commit()

    service.request_code(db_session, "new@example.cz")
    assert [row.email for row in db_session.scalars(select(LoginCode))] == ["new@example.cz"]


def test_listed_admin_email_becomes_admin_on_first_login(
    db_session: Session, service: AuthService, sender: RecordingSender, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(config, "ADMIN_EMAILS", frozenset({"boss@example.cz"}))
    service.request_code(db_session, "Boss@Example.cz")
    assert service.verify_code(db_session, "boss@example.cz", sender.last_code).is_admin is True


def test_listed_admin_email_is_promoted_if_the_account_already_existed(
    db_session: Session, service: AuthService, sender: RecordingSender, monkeypatch: pytest.MonkeyPatch
) -> None:
    service.request_code(db_session, "boss@example.cz")
    assert service.verify_code(db_session, "boss@example.cz", sender.last_code).is_admin is False

    monkeypatch.setattr(config, "ADMIN_EMAILS", frozenset({"boss@example.cz"}))
    service.request_code(db_session, "boss@example.cz")
    assert service.verify_code(db_session, "boss@example.cz", sender.last_code).is_admin is True


def test_unlisted_email_is_never_admin_and_removing_from_list_does_not_demote(
    db_session: Session, service: AuthService, sender: RecordingSender, monkeypatch: pytest.MonkeyPatch
) -> None:
    service.request_code(db_session, "jana@example.cz")
    assert service.verify_code(db_session, "jana@example.cz", sender.last_code).is_admin is False

    monkeypatch.setattr(config, "ADMIN_EMAILS", frozenset({"boss@example.cz"}))
    service.request_code(db_session, "boss@example.cz")
    service.verify_code(db_session, "boss@example.cz", sender.last_code)
    monkeypatch.setattr(config, "ADMIN_EMAILS", frozenset())
    service.request_code(db_session, "boss@example.cz")
    assert service.verify_code(db_session, "boss@example.cz", sender.last_code).is_admin is True


def test_disabled_account_cannot_log_in(db_session: Session, service: AuthService, sender: RecordingSender) -> None:
    service.request_code(db_session, "jana@example.cz")
    user = service.verify_code(db_session, "jana@example.cz", sender.last_code)
    db_session.get(User, user.id).is_active = False
    db_session.commit()

    service.request_code(db_session, "jana@example.cz")
    with pytest.raises(AuthError) as exc_info:
        service.verify_code(db_session, "jana@example.cz", sender.last_code)
    assert exc_info.value.code == "account_disabled"


def test_get_active_user_reflects_current_db_state(
    db_session: Session, service: AuthService, sender: RecordingSender
) -> None:
    service.request_code(db_session, "jana@example.cz")
    user = service.verify_code(db_session, "jana@example.cz", sender.last_code)
    assert AuthService.get_active_user(db_session, user.id) == user

    db_session.get(User, user.id).is_active = False
    db_session.commit()
    assert AuthService.get_active_user(db_session, user.id) is None
    assert AuthService.get_active_user(db_session, 99999) is None

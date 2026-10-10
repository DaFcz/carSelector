"""The chat abuse limits in `app/services/conversation.py` (message length,
per-client and per-conversation caps, idle expiry, size cap) and how the
REST API reports them. Wizard turns are used where a turn has to succeed,
since they don't need the AI requirement-extraction step (no API key in
tests)."""

import pytest
from fastapi.testclient import TestClient

from app.core import config
from app.schemas.common import Money
from app.schemas.requirement import StructuredRequirements
from app.services.conversation import ConversationLimitError, ConversationOrchestrator, UnknownConversationError
from tests.conftest import SeededData

REQUIREMENTS = StructuredRequirements(budget_max=Money(amount=1_100_000, currency="CZK"))


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


class NoExplanations:
    def explain(self, *_args, **_kwargs) -> None:
        return None


def _orchestrator(clock: FakeClock | None = None) -> ConversationOrchestrator:
    return ConversationOrchestrator(explanation_generator=NoExplanations(), clock=clock or FakeClock())  # type: ignore[arg-type]


def _limit_code(call) -> str:
    with pytest.raises(ConversationLimitError) as exc_info:
        call()
    return exc_info.value.code


def test_too_long_message_is_refused_before_any_ai_call(seeded_session: SeededData, monkeypatch) -> None:
    monkeypatch.setattr(config, "CHAT_MAX_MESSAGE_LENGTH", 10)
    orchestrator = _orchestrator()
    conversation_id, _ = orchestrator.start_conversation()
    code = _limit_code(lambda: orchestrator.handle_message(seeded_session.session, conversation_id, "x" * 11))
    assert code == "message_too_long"


def test_messages_per_client_are_rate_limited_across_conversations(seeded_session: SeededData, monkeypatch) -> None:
    monkeypatch.setattr(config, "CHAT_MAX_MESSAGES_PER_CLIENT_HOUR", 2)
    clock = FakeClock()
    orchestrator = _orchestrator(clock)
    db = seeded_session.session
    first, _ = orchestrator.start_conversation(client_key="1.2.3.4")
    second, _ = orchestrator.start_conversation(client_key="1.2.3.4")
    orchestrator.handle_wizard_answers(db, first, REQUIREMENTS, "summary")
    orchestrator.handle_wizard_answers(db, second, REQUIREMENTS, "summary")

    assert _limit_code(lambda: orchestrator.handle_wizard_answers(db, first, REQUIREMENTS, "summary")) == "rate_limited"
    # Another client isn't affected, and the limit lifts after an hour.
    other, _ = orchestrator.start_conversation(client_key="5.6.7.8")
    orchestrator.handle_wizard_answers(db, other, REQUIREMENTS, "summary")
    clock.now += 3601
    orchestrator.handle_wizard_answers(db, first, REQUIREMENTS, "summary")


def test_without_a_client_key_the_conversation_is_limited(seeded_session: SeededData, monkeypatch) -> None:
    monkeypatch.setattr(config, "CHAT_MAX_MESSAGES_PER_CLIENT_HOUR", 1)
    orchestrator = _orchestrator()
    db = seeded_session.session
    conversation_id, _ = orchestrator.start_conversation()
    orchestrator.handle_wizard_answers(db, conversation_id, REQUIREMENTS, "summary")
    code = _limit_code(lambda: orchestrator.handle_wizard_answers(db, conversation_id, REQUIREMENTS, "summary"))
    assert code == "rate_limited"


def test_conversations_started_per_client_are_rate_limited(monkeypatch) -> None:
    monkeypatch.setattr(config, "CHAT_MAX_CONVERSATIONS_PER_CLIENT_HOUR", 2)
    orchestrator = _orchestrator()
    orchestrator.start_conversation(client_key="1.2.3.4")
    orchestrator.start_conversation(client_key="1.2.3.4")
    assert _limit_code(lambda: orchestrator.start_conversation(client_key="1.2.3.4")) == "rate_limited"


def test_conversation_length_is_capped(seeded_session: SeededData, monkeypatch) -> None:
    monkeypatch.setattr(config, "CHAT_MAX_MESSAGES_PER_CONVERSATION", 2)
    orchestrator = _orchestrator()
    db = seeded_session.session
    conversation_id, _ = orchestrator.start_conversation()
    for _ in range(2):
        orchestrator.handle_wizard_answers(db, conversation_id, REQUIREMENTS, "summary")
    code = _limit_code(lambda: orchestrator.handle_wizard_answers(db, conversation_id, REQUIREMENTS, "summary"))
    assert code == "conversation_too_long"


def test_idle_conversations_expire(seeded_session: SeededData, monkeypatch) -> None:
    monkeypatch.setattr(config, "CHAT_CONVERSATION_IDLE_MINUTES", 10)
    clock = FakeClock()
    orchestrator = _orchestrator(clock)
    db = seeded_session.session
    conversation_id, _ = orchestrator.start_conversation()
    clock.now += 9 * 60
    orchestrator.handle_wizard_answers(db, conversation_id, REQUIREMENTS, "summary")  # activity resets the clock
    clock.now += 9 * 60
    orchestrator.handle_wizard_answers(db, conversation_id, REQUIREMENTS, "summary")
    clock.now += 11 * 60
    with pytest.raises(UnknownConversationError):
        orchestrator.handle_wizard_answers(db, conversation_id, REQUIREMENTS, "summary")


def test_least_recently_used_conversation_is_dropped_when_full(seeded_session: SeededData, monkeypatch) -> None:
    monkeypatch.setattr(config, "CHAT_MAX_CONVERSATIONS", 2)
    orchestrator = _orchestrator()
    db = seeded_session.session
    first, _ = orchestrator.start_conversation()
    second, _ = orchestrator.start_conversation()
    orchestrator.handle_wizard_answers(db, first, REQUIREMENTS, "summary")  # second is now least recently used
    orchestrator.start_conversation()

    orchestrator.handle_wizard_answers(db, first, REQUIREMENTS, "summary")
    with pytest.raises(UnknownConversationError):
        orchestrator.handle_wizard_answers(db, second, REQUIREMENTS, "summary")


def test_api_reports_too_long_message_as_422(client: TestClient, monkeypatch) -> None:
    monkeypatch.setattr(config, "CHAT_MAX_MESSAGE_LENGTH", 10)
    conversation_id = client.post("/api/conversations").json()["conversation_id"]
    response = client.post(f"/api/conversations/{conversation_id}/messages", json={"text": "x" * 11})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "message_too_long"


def test_api_reports_rate_limit_as_429(client: TestClient, monkeypatch) -> None:
    from app.api import conversations as conversations_api

    def _refuse(*_args, **_kwargs):
        raise ConversationLimitError("rate_limited")

    monkeypatch.setattr(conversations_api.orchestrator, "start_conversation", _refuse)
    response = client.post("/api/conversations")
    assert response.status_code == 429
    assert response.json()["error"]["code"] == "rate_limited"

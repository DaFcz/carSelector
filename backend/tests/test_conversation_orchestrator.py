"""Covers `ConversationOrchestrator.handle_wizard_answers` - the wizard's
entry point into the same conversation state, recommend, and explain
pipeline `handle_message` uses for chat turns (see
`app/services/conversation.py` and `app/ui/components/wizard.py`).
Exercises the real recommendation engine against the seeded catalog
(same fixture the API test suite uses), not a mock, since ranking
correctness is the point.
"""

from datetime import UTC, date, datetime

import pytest
from sqlalchemy.orm import Session

import app.services.conversation as conversation_module
from app.models import Brand, CarModel, Configuration, Powertrain, Price, SourceDocument, Trim
from app.models.enums import DocumentType, Drivetrain, FuelType
from app.schemas.common import Money
from app.schemas.requirement import StructuredRequirements
from app.schemas.vehicle import VehicleSummary
from app.services.conversation import ConversationOrchestrator, UnknownConversationError
from tests.conftest import SeededData


def test_handle_wizard_answers_searches_without_ai_extraction(seeded_session: SeededData) -> None:
    # No ANTHROPIC_API_KEY in the test environment - unlike handle_message,
    # this must still succeed and return ranked vehicles, since the wizard
    # skips the AI requirement-extraction step entirely (see
    # WizardState.to_structured_requirements). Only the per-vehicle
    # explanation step (best-effort) touches the AI layer.
    orchestrator = ConversationOrchestrator()
    conversation_id, _ = orchestrator.start_conversation()

    requirements = StructuredRequirements(
        body_type="SUV",
        budget_max=Money(amount=1_100_000, currency="CZK"),
        fuel_type="petrol",
        drivetrain=Drivetrain.awd,
    )

    result = orchestrator.handle_wizard_answers(
        seeded_session.session, conversation_id, requirements, "Vyplnil(a) jsem průvodce: ..."
    )

    assert result.searched is True
    assert len(result.vehicles) == 2
    # AWD is a soft preference (see RecommendationEngine._score) - the AWD
    # configuration should outrank the FWD one and be flagged top_pick.
    assert result.vehicles[0].configuration_id == seeded_session.config_centre_awd_id
    assert result.vehicles[0].top_pick is True
    assert result.vehicles[0].explanation is None  # AI layer not configured - degrades gracefully.


def test_handle_wizard_answers_records_requirements_for_the_drawer(seeded_session: SeededData) -> None:
    orchestrator = ConversationOrchestrator()
    conversation_id, _ = orchestrator.start_conversation()

    requirements = StructuredRequirements(
        budget_max=Money(amount=1_100_000, currency="CZK"), notes="Preference značky: Škoda"
    )

    result = orchestrator.handle_wizard_answers(seeded_session.session, conversation_id, requirements, "summary")

    labels = {card.label: card.value for card in result.requirements}
    assert labels["Rozpočet"] == "1,100,000 CZK"
    assert labels["Poznámky"] == "Preference značky: Škoda"


def test_handle_wizard_answers_merges_onto_a_prior_chat_turn(seeded_session: SeededData) -> None:
    # A wizard turn after a chat turn (or vice versa) should merge onto the
    # same accumulated StructuredRequirements, not reset it - the wizard is
    # an alternate input channel into one conversation, not a separate flow.
    orchestrator = ConversationOrchestrator()
    conversation_id, _ = orchestrator.start_conversation()

    orchestrator.handle_wizard_answers(
        seeded_session.session, conversation_id, StructuredRequirements(body_type="SUV"), "first"
    )
    result = orchestrator.handle_wizard_answers(
        seeded_session.session,
        conversation_id,
        StructuredRequirements(budget_max=Money(amount=900_000, currency="CZK")),
        "second",
    )

    labels = {card.label for card in result.requirements}
    assert "Karoserie" in labels
    assert "Rozpočet" in labels


def test_handle_wizard_answers_raises_for_unknown_conversation(seeded_session: SeededData) -> None:
    orchestrator = ConversationOrchestrator()
    with pytest.raises(UnknownConversationError):
        orchestrator.handle_wizard_answers(seeded_session.session, "not-a-real-id", StructuredRequirements(), "summary")


class _CountingExplanationGenerator:
    """Fake `ExplanationGenerator` (duck-typed, see `explain`'s matching
    signature) that just counts how many times it was actually called,
    for `test_handle_wizard_answers_caps_ai_explanations_not_result_count`
    below - real explanations aren't the point of that test, only how many
    get requested."""

    def __init__(self) -> None:
        self.calls = 0

    def explain(self, vehicle: VehicleSummary, requirements: StructuredRequirements, *, language: str = "cs") -> str:
        self.calls += 1
        return "stub explanation"


def _add_cheap_configs(session: Session, count: int, id_offset: int) -> None:
    """Adds `count` cheap (300,000 Kč), otherwise-identical SUV
    configurations directly to `session` - enough to exceed
    `ConversationOrchestrator.EXPLANATION_LIMIT` so the cap below actually
    gets exercised."""
    brand = Brand(id=id_offset, slug="bulk", name="Bulk")
    session.add(brand)
    session.flush()

    model = CarModel(id=id_offset, brand_id=brand.id, slug="bulk-model", name="Model", category="SUV")
    session.add(model)
    session.flush()

    source_doc = SourceDocument(
        id=id_offset,
        model_id=model.id,
        file_path="storage/cars/bulk/pricelist.pdf",
        document_type=DocumentType.price_list,
        market="CZ",
        locale="cs-CZ",
        effective_date=date(2026, 1, 1),
        retrieved_at=datetime.now(UTC),
    )
    session.add(source_doc)
    session.flush()

    for i in range(count):
        row_id = id_offset + i
        trim = Trim(id=row_id, model_id=model.id, name=f"Trim {i}", display_order=i)
        session.add(trim)
        session.flush()

        powertrain = Powertrain(
            id=row_id, model_id=model.id, fuel_type=FuelType.petrol, transmission="automatic", drivetrain=Drivetrain.fwd
        )
        session.add(powertrain)
        session.flush()

        configuration = Configuration(id=row_id, trim_id=trim.id, powertrain_id=powertrain.id)
        session.add(configuration)
        session.flush()

        session.add(
            Price(
                id=row_id,
                configuration_id=configuration.id,
                source_document_id=source_doc.id,
                market="CZ",
                currency="CZK",
                list_price=300_000,
                price_incl_vat=300_000,
                valid_from=date(2026, 1, 1),
                valid_to=None,
                scraped_at=datetime.now(UTC),
            )
        )
    session.commit()


def test_handle_wizard_answers_caps_ai_explanations_not_result_count(seeded_session: SeededData) -> None:
    # Reported bug: a budget-only wizard answer matching far more than 10
    # vehicles returned only 10. The fix returns every match, but must
    # still bound the number of AI explanation calls per turn (each
    # `ExplanationGenerator.explain` is its own Claude API call) -
    # `ConversationOrchestrator.EXPLANATION_LIMIT` is that separate cap.
    _add_cheap_configs(seeded_session.session, count=25, id_offset=1000)
    assert conversation_module.ConversationOrchestrator.EXPLANATION_LIMIT < 25

    fake_generator = _CountingExplanationGenerator()
    orchestrator = ConversationOrchestrator(explanation_generator=fake_generator)  # type: ignore[arg-type]
    conversation_id, _ = orchestrator.start_conversation()

    result = orchestrator.handle_wizard_answers(
        seeded_session.session,
        conversation_id,
        StructuredRequirements(budget_max=Money(amount=1_000_000, currency="CZK")),
        "Vyplnil(a) jsem průvodce: rozpočet do 1 000 000 Kč",
    )

    assert len(result.vehicles) == 25 + 1  # + the seeded fixture's own in-budget Mazda config
    assert fake_generator.calls == conversation_module.ConversationOrchestrator.EXPLANATION_LIMIT
    explained_count = sum(1 for v in result.vehicles if v.explanation == "stub explanation")
    assert explained_count == conversation_module.ConversationOrchestrator.EXPLANATION_LIMIT


def test_english_conversation_greets_and_labels_in_english(seeded_session: SeededData) -> None:
    orchestrator = ConversationOrchestrator(explanation_generator=_CountingExplanationGenerator())
    conversation_id, intro = orchestrator.start_conversation("en")
    assert intro.startswith("Hi!")

    response = orchestrator.handle_wizard_answers(
        seeded_session.session,
        conversation_id,
        StructuredRequirements(budget_max=Money(amount=1_100_000, currency="CZK")),
        "I filled in the guide",
    )
    assert {card.label for card in response.requirements} == {"Budget"}
    assert response.assistant_text.startswith("Based on what you've told me")


def test_unknown_language_falls_back_to_czech() -> None:
    _, intro = ConversationOrchestrator().start_conversation("de")
    assert intro.startswith("Ahoj!")

"""Covers app/ui/state.py's ConversationState/CatalogState against the
real service layer + seeded in-memory DB (via `patch_ui_session` -
see conftest.py). Exercises the same "browsing mode load", "AI not
configured", and "restart" paths verified manually in-browser during the
NiceGUI migration, as an automated regression net - not a NiceGUI
`User`-fixture test: those need a `main_file` containing a literal
`ui.run()` call (per NiceGUI 3.x's testing docs), which doesn't fit this
app's `ui.run_with(app, ...)`-mounted-on-FastAPI structure, so this
exercises the state layer directly instead - the layer that actually
talks to the database/orchestrator and carries the real risk, independent
of how the DOM ends up rendering it.
"""

from app.models.enums import Drivetrain
from app.schemas.requirement import StructuredRequirements
from app.ui.state import CatalogState, ConversationState, WizardState
from tests.conftest import SeededData


async def test_catalog_state_loads_brands(patch_ui_session, seeded_session: SeededData) -> None:
    state = CatalogState()
    await state.load_brands()
    assert [b.name for b in state.brands] == ["Mazda", "Volkswagen"]


async def test_catalog_state_filters_by_drivetrain(patch_ui_session, seeded_session: SeededData) -> None:
    state = CatalogState(drivetrain=Drivetrain.awd)
    await state.load_first_page(sort=None)
    assert state.total == 2
    # Default order is configuration.id ascending - the Mazda AWD
    # configuration was seeded first, so it still sorts first.
    assert state.cars[0].configuration_id == seeded_session.config_centre_awd_id


async def test_catalog_state_filters_by_brand_id(patch_ui_session, seeded_session: SeededData) -> None:
    state = CatalogState(brand_id=999999)
    await state.load_first_page(sort=None)
    assert state.total == 0
    assert state.cars == []


async def test_catalog_state_loads_seeded_vehicles(patch_ui_session, seeded_session: SeededData) -> None:
    state = CatalogState()
    await state.load_first_page(sort=None)
    assert state.total == 4
    assert len(state.cars) == 4
    assert not state.error


async def test_catalog_state_has_more_is_false_once_fully_loaded(patch_ui_session, seeded_session: SeededData) -> None:
    state = CatalogState(page_size=20)
    await state.load_first_page(sort=None)
    assert state.has_more is False


async def test_catalog_state_load_more_is_a_noop_when_nothing_left(patch_ui_session, seeded_session: SeededData) -> None:
    state = CatalogState()
    await state.load_first_page(sort=None)
    cars_before = list(state.cars)
    await state.load_more(sort=None)
    assert state.cars == cars_before


async def test_conversation_state_begin_starts_and_seeds_intro_message(patch_ui_session) -> None:
    state = ConversationState()
    await state.begin()
    assert state.conversation_id is not None
    assert len(state.messages) == 1
    assert state.messages[0][0] == "assistant"
    assert not state.is_loading


async def test_conversation_state_send_without_api_key_sets_ai_not_configured(patch_ui_session) -> None:
    # No ANTHROPIC_API_KEY in the test environment - see app/ai/client.py
    # and backend/README.md's "degrades to a 503 ai_not_configured
    # response" note, exercised here the same way the API test suite
    # exercises it for the REST endpoint.
    state = ConversationState()
    await state.begin()
    await state.send("Chci rodinné auto do 900 tisíc.")
    assert state.error == "ai_not_configured"
    assert not state.is_sending
    # The user's message still landed in the transcript even though the
    # AI call failed - matches ChatColumn's behavior of showing what was
    # sent regardless of the response outcome.
    assert state.messages[-1] == ("user", "Chci rodinné auto do 900 tisíc.")


async def test_conversation_state_send_ignores_blank_text(patch_ui_session) -> None:
    state = ConversationState()
    await state.begin()
    message_count = len(state.messages)
    await state.send("   ")
    assert len(state.messages) == message_count


async def test_conversation_state_restart_resets_and_begins_again(patch_ui_session) -> None:
    state = ConversationState()
    await state.begin()
    first_id = state.conversation_id
    state.drawer_open = True

    await state.restart()

    assert state.conversation_id is not None
    assert state.conversation_id != first_id
    assert state.drawer_open is False
    assert state.has_narrowed is False
    assert len(state.messages) == 1


def test_conversation_state_toggle_and_close_drawer() -> None:
    state = ConversationState()
    assert state.drawer_open is False
    state.toggle_drawer()
    assert state.drawer_open is True
    state.close_drawer()
    assert state.drawer_open is False


async def test_conversation_state_send_wizard_answers_works_without_api_key(
    patch_ui_session, seeded_session: SeededData
) -> None:
    # Unlike send(), the wizard path skips AI requirement extraction
    # entirely (see WizardState.to_structured_requirements), so it must
    # still search and populate results without ANTHROPIC_API_KEY set.
    state = ConversationState()
    await state.begin()

    wizard = WizardState()
    wizard.open_wizard()
    wizard.body_type = "SUV"
    wizard.needs_awd = True

    await state.send_wizard_answers(wizard.to_structured_requirements(), "Vyplnil(a) jsem průvodce: ...")

    assert state.error is None
    assert state.has_narrowed is True
    # No budget filter - every seeded SUV (both Mazda configs, both VW
    # configs) qualifies; AWD is a soft preference so the cheaper of the
    # two AWD vehicles (Mazda's) still ranks first.
    assert len(state.cars) == 4
    assert state.cars[0].configuration_id == seeded_session.config_centre_awd_id
    assert state.messages[-2] == ("user", "Vyplnil(a) jsem průvodce: ...")
    assert state.messages[-1][0] == "assistant"


async def test_conversation_state_send_wizard_answers_noop_before_begin(patch_ui_session) -> None:
    state = ConversationState()
    await state.send_wizard_answers(StructuredRequirements(), "summary")
    assert state.messages == []


def test_wizard_state_open_wizard_resets_all_answers() -> None:
    wizard = WizardState()
    wizard.step = 4
    wizard.budget = 900_000
    wizard.brand_pref = "Škoda"

    wizard.open_wizard()

    assert wizard.is_open is True
    assert wizard.step == 0
    assert wizard.budget is None
    assert wizard.brand_pref == ""


def test_wizard_state_go_next_and_go_back_are_capped() -> None:
    wizard = WizardState()
    wizard.go_back()
    assert wizard.step == 0

    for _ in range(WizardState.STEP_COUNT + 2):
        wizard.go_next()
    assert wizard.step == WizardState.STEP_COUNT - 1
    assert wizard.is_last_step is True


def test_wizard_state_to_structured_requirements_maps_all_answers() -> None:
    wizard = WizardState()
    wizard.budget = 900_000
    wizard.usage = "family"
    wizard.seats = 5
    wizard.body_type = "SUV"
    wizard.needs_awd = True
    wizard.fuel_pattern = "diesel"
    wizard.annual_km = 20_000
    wizard.cargo_need = "trailer"
    wizard.brand_pref = "Preferuji Škodu"
    wizard.priority = "repairs"

    requirements = wizard.to_structured_requirements()

    assert requirements.body_type == "SUV"
    assert requirements.min_seats == 5
    assert requirements.budget_max is not None
    assert requirements.budget_max.amount == 900_000
    assert requirements.budget_max.currency == "CZK"
    assert requirements.fuel_type == "diesel"
    assert requirements.drivetrain == Drivetrain.awd
    assert requirements.priorities == ["family", "repairs", "cargo"]
    assert requirements.notes == "Preference značky: Preferuji Škodu; Roční nájezd přibližně 20000 km"


def test_wizard_state_to_structured_requirements_is_empty_when_everything_is_skipped() -> None:
    requirements = WizardState().to_structured_requirements()

    assert requirements.body_type is None
    assert requirements.min_seats is None
    assert requirements.budget_max is None
    assert requirements.fuel_type is None
    assert requirements.drivetrain is None
    assert requirements.priorities == []
    assert requirements.notes is None


def test_wizard_state_needs_awd_false_leaves_drivetrain_unset() -> None:
    wizard = WizardState()
    wizard.needs_awd = False

    assert wizard.to_structured_requirements().drivetrain is None


async def test_conversation_state_send_surfaces_ai_provider_error_code(patch_ui_session, monkeypatch, caplog) -> None:
    from app.ai.errors import AiProviderError
    from app.ui import state as state_module

    def _reject(*_args, **_kwargs):
        raise AiProviderError("ai_invalid_key", "Invalid API Key")

    monkeypatch.setattr(state_module.orchestrator, "handle_message", _reject)
    state = ConversationState()
    await state.begin()
    with caplog.at_level("WARNING"):
        await state.send("Chci rodinné auto.")

    assert state.error == "ai_invalid_key"
    assert not state.is_sending
    assert "ai_invalid_key" in caplog.text  # logged, not silently swallowed


async def test_conversation_state_send_logs_unexpected_errors(patch_ui_session, monkeypatch, caplog) -> None:
    from app.ui import state as state_module

    def _explode(*_args, **_kwargs):
        raise ValueError("kaboom")

    monkeypatch.setattr(state_module.orchestrator, "handle_message", _explode)
    state = ConversationState()
    await state.begin()
    await state.send("Chci rodinné auto.")

    assert state.error == "unknown_error"
    assert "kaboom" in caplog.text

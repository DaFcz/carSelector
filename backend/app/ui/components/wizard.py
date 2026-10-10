"""Guided step-by-step alternative to the free-text chat, for
non-technical users to build `StructuredRequirements` without needing to
type - see `doc/ai/wizard-questions.md` for the underlying question
design and rationale. `WizardState` (`app/ui/state.py`) owns the
deterministic answers-to-requirements mapping; this module only renders
the ten steps/their options and turns a finished `WizardState` into a
human-readable recap for the chat transcript.
"""

from collections.abc import Awaitable, Callable

from nicegui import ui

from app.schemas.requirement import StructuredRequirements
from app.ui.i18n import t
from app.ui.state import WizardState

_USAGE_OPTIONS = ("commute", "family", "cargo", "mixed")
_BODY_TYPE_OPTIONS = ("Hatchback", "Kombi", "SUV", "MPV")
_FUEL_OPTIONS = ("electric", "hybrid", "diesel", "petrol")
_CARGO_OPTIONS = ("stroller", "sports", "tools", "trailer", "none")
_PRIORITY_OPTIONS = ("cost", "repairs", "power", "comfort")
# Pre-filled annual mileage: roughly the average for a Czech passenger car,
# so the arrows start from a realistic value instead of 0. Only the input
# is pre-filled - "Přeskočit" still leaves `annual_km` unset.
DEFAULT_ANNUAL_KM = 15_000
ANNUAL_KM_STEP = 1_000

_OPTION_BUTTON_CLASSES = "w-full rounded-control border px-4 py-2.5 text-left text-[13px] font-semibold "
_OPTION_SELECTED = "border-accent bg-accent text-accent-text"
_OPTION_UNSELECTED = "border-border bg-panel-2 text-text"


def summary_text(wizard: WizardState) -> str:
    """Builds the human-readable recap shown as the wizard's "user" chat
    bubble - there is no free text to show instead, since every answer
    came from a button/number field.

    Args:
        wizard: The finished wizard, about to be submitted.

    Returns:
        e.g. `"Vyplnil(a) jsem průvodce: rozpočet do 900 000 Kč; ..."` -
        one short fragment per answered question, skipped ones omitted,
        or just the intro phrase if every question was skipped.
    """
    fragments: list[str] = []
    if wizard.budget is not None:
        amount = f"{wizard.budget:,.0f}".replace(",", " ")
        fragments.append(t("wizard.questions.budget.summary", amount=amount))
    if wizard.usage is not None:
        fragments.append(t(f"wizard.questions.usage.options.{wizard.usage}"))
    if wizard.seats is not None:
        fragments.append(t("wizard.questions.seats.summary", count=wizard.seats))
    if wizard.body_type is not None:
        fragments.append(t(f"wizard.questions.bodyType.options.{wizard.body_type}"))
    if wizard.needs_awd:
        fragments.append(t("wizard.questions.awd.yes"))
    if wizard.fuel_pattern is not None:
        fragments.append(t(f"wizard.questions.fuel.options.{wizard.fuel_pattern}"))
    if wizard.annual_km is not None:
        fragments.append(t("wizard.questions.mileage.summary", km=wizard.annual_km))
    if wizard.cargo_need is not None and wizard.cargo_need != "none":
        fragments.append(t(f"wizard.questions.cargo.options.{wizard.cargo_need}"))
    if wizard.brand_pref.strip():
        fragments.append(wizard.brand_pref.strip())
    if wizard.priority is not None:
        fragments.append(t(f"wizard.questions.priority.options.{wizard.priority}"))

    intro = t("wizard.summaryIntro")
    return f"{intro}: {'; '.join(fragments)}" if fragments else intro


def _progress(wizard: WizardState) -> None:
    """Renders the "Otázka X z 10" label and a segmented progress bar."""
    ui.label(t("wizard.progress", step=wizard.step + 1, total=WizardState.STEP_COUNT)).classes(
        "text-[11px] font-bold uppercase tracking-wide text-subtext"
    )
    with ui.row().classes("mt-1.5 mb-5 h-1.5 w-full gap-1"):
        for i in range(WizardState.STEP_COUNT):
            ui.element("div").classes(
                "h-full flex-1 rounded-full " + ("bg-accent" if i <= wizard.step else "bg-border")
            )


def _option_list(options: tuple[str, ...], labels_path: str, on_pick: Callable[[str], Awaitable[None]]) -> None:
    """Renders one column of single-choice buttons, each of which sets an
    answer and advances in one click - the fastest path for a
    non-technical user who only needs to recognize the right option.

    Args:
        options: Identifiers in display order.
        labels_path: Dotted i18n path whose children are keyed by each
            option identifier (e.g. `"wizard.questions.usage.options"`).
        on_pick: Called (and awaited by NiceGUI) with the clicked
            option's identifier.
    """
    with ui.column().classes("w-full gap-2"):
        for option in options:
            ui.button(t(f"{labels_path}.{option}"), on_click=lambda o=option: on_pick(o)).props(
                "no-caps unelevated align-left"
            ).classes(_OPTION_BUTTON_CLASSES + _OPTION_UNSELECTED)


def wizard_dialog(
    wizard: WizardState, on_finish: Callable[[StructuredRequirements, str], Awaitable[None]]
) -> Callable[[], None]:
    """Builds the (initially closed) wizard dialog.

    Args:
        wizard: Per-connection wizard state - mutated in place as the
            user answers/navigates. `app/ui/pages.py` opens it by calling
            `wizard.open_wizard()` and the returned refresh function, then
            `dialog.open()` via the returned `open_` callable.
        on_finish: Awaited with the built `StructuredRequirements` and the
            summary text once the user completes the last step, so the
            caller (see `app/ui/pages.py`) can run the actual search. The
            dialog is already closed by the time this is called.

    Returns:
        A zero-argument function that opens the dialog at the wizard's
        current step - call after `wizard.open_wizard()`.
    """
    # `dialog-mobile-full` (see app/ui/styles.py): fullscreen on phones.
    with (
        ui.dialog().classes("dialog-mobile-full") as dialog,
        ui.card().classes(
            "w-full max-w-[480px] overflow-y-auto rounded-card border border-border bg-panel p-4 md:p-6 shadow-card "
            "animate-fade-in"
        ),
    ):

        async def _advance() -> None:
            """Moves past the current step - finalizes and closes on the
            last step, otherwise renders the next one. Shared by every
            step's forward action (choice click, Next/Finish button, and
            Skip), since "skip the last question" and "finish" are the
            same action once there is no next step to show.
            """
            if wizard.is_last_step:
                dialog.close()
                requirements = wizard.to_structured_requirements()
                text = summary_text(wizard)
                await on_finish(requirements, text)
                return
            wizard.go_next()
            _content.refresh()

        async def _pick(setter: Callable[[str], None], value: str) -> None:
            setter(value)
            await _advance()

        @ui.refreshable
        def _content() -> None:
            with ui.row().classes("w-full items-start justify-between gap-3"):
                ui.label(t("wizard.title")).classes("text-[16px] font-bold text-text")
                ui.button(t("wizard.close"), on_click=dialog.close).props("flat no-caps").classes(
                    "shrink-0 rounded-control border border-border bg-panel-2 px-3 py-1.5 text-[13px] font-semibold text-text"
                )
            _progress(wizard)

            step = wizard.step
            if step == 0:
                ui.label(t("wizard.questions.budget.title")).classes("mb-3 text-[14px] font-semibold text-text")
                budget_input = (
                    ui.number(placeholder=t("wizard.questions.budget.placeholder"), value=wizard.budget, min=0)
                    .props(f'borderless dense suffix="{t("wizard.questions.budget.unit")}"')
                    .classes(
                        "w-full rounded-control border border-border bg-panel-2 px-3.5 py-2.5 text-[14px] text-text"
                    )
                )

                async def _next_budget() -> None:
                    wizard.budget = budget_input.value
                    await _advance()

                _footer(wizard, _content.refresh, _advance, _next_budget)
            elif step == 1:
                ui.label(t("wizard.questions.usage.title")).classes("mb-3 text-[14px] font-semibold text-text")
                _option_list(_USAGE_OPTIONS, "wizard.questions.usage.options", lambda v: _pick(_set_usage, v))
                _footer(wizard, _content.refresh, _advance, None)
            elif step == 2:
                ui.label(t("wizard.questions.seats.title")).classes("mb-3 text-[14px] font-semibold text-text")
                seats_input = (
                    ui.number(placeholder=t("wizard.questions.seats.placeholder"), value=wizard.seats, min=1, max=9)
                    .props("borderless dense")
                    .classes(
                        "w-full rounded-control border border-border bg-panel-2 px-3.5 py-2.5 text-[14px] text-text"
                    )
                )

                async def _next_seats() -> None:
                    wizard.seats = int(seats_input.value) if seats_input.value is not None else None
                    await _advance()

                _footer(wizard, _content.refresh, _advance, _next_seats)
            elif step == 3:
                ui.label(t("wizard.questions.bodyType.title")).classes("mb-1 text-[14px] font-semibold text-text")
                ui.label(t("wizard.questions.bodyType.hint")).classes("mb-3 text-[12.5px] text-subtext")
                _option_list(
                    _BODY_TYPE_OPTIONS, "wizard.questions.bodyType.options", lambda v: _pick(_set_body_type, v)
                )
                _footer(wizard, _content.refresh, _advance, None)
            elif step == 4:
                ui.label(t("wizard.questions.awd.title")).classes("mb-1 text-[14px] font-semibold text-text")
                ui.label(t("wizard.questions.awd.hint")).classes("mb-3 text-[12.5px] text-subtext")
                with ui.column().classes("w-full gap-2"):
                    ui.button(t("wizard.questions.awd.yes"), on_click=lambda: _pick(_set_awd, "yes")).props(
                        "no-caps unelevated align-left"
                    ).classes(_OPTION_BUTTON_CLASSES + _OPTION_UNSELECTED)
                    ui.button(t("wizard.questions.awd.no"), on_click=lambda: _pick(_set_awd, "no")).props(
                        "no-caps unelevated align-left"
                    ).classes(_OPTION_BUTTON_CLASSES + _OPTION_UNSELECTED)
                _footer(wizard, _content.refresh, _advance, None)
            elif step == 5:
                ui.label(t("wizard.questions.fuel.title")).classes("mb-3 text-[14px] font-semibold text-text")
                _option_list(_FUEL_OPTIONS, "wizard.questions.fuel.options", lambda v: _pick(_set_fuel, v))
                _footer(wizard, _content.refresh, _advance, None)
            elif step == 6:
                ui.label(t("wizard.questions.mileage.title")).classes("mb-3 text-[14px] font-semibold text-text")
                mileage_input = (
                    ui.number(
                        placeholder=t("wizard.questions.mileage.placeholder"),
                        value=wizard.annual_km if wizard.annual_km is not None else DEFAULT_ANNUAL_KM,
                        min=0,
                        step=ANNUAL_KM_STEP,
                    )
                    .props('borderless dense suffix="km"')
                    .mark("mileage-input")
                    .classes(
                        "w-full rounded-control border border-border bg-panel-2 px-3.5 py-2.5 text-[14px] text-text"
                    )
                )

                async def _next_mileage() -> None:
                    wizard.annual_km = int(mileage_input.value) if mileage_input.value is not None else None
                    await _advance()

                _footer(wizard, _content.refresh, _advance, _next_mileage)
            elif step == 7:
                ui.label(t("wizard.questions.cargo.title")).classes("mb-3 text-[14px] font-semibold text-text")
                _option_list(_CARGO_OPTIONS, "wizard.questions.cargo.options", lambda v: _pick(_set_cargo, v))
                _footer(wizard, _content.refresh, _advance, None)
            elif step == 8:
                ui.label(t("wizard.questions.brand.title")).classes("mb-3 text-[14px] font-semibold text-text")
                brand_input = (
                    ui.input(placeholder=t("wizard.questions.brand.placeholder"), value=wizard.brand_pref)
                    .props("borderless dense")
                    .classes(
                        "w-full rounded-control border border-border bg-panel-2 px-3.5 py-2.5 text-[14px] text-text"
                    )
                )

                async def _next_brand() -> None:
                    wizard.brand_pref = brand_input.value or ""
                    await _advance()

                _footer(wizard, _content.refresh, _advance, _next_brand)
            else:
                ui.label(t("wizard.questions.priority.title")).classes("mb-3 text-[14px] font-semibold text-text")
                _option_list(_PRIORITY_OPTIONS, "wizard.questions.priority.options", lambda v: _pick(_set_priority, v))
                _footer(wizard, _content.refresh, _advance, None)

        def _set_usage(value: str) -> None:
            wizard.usage = value

        def _set_body_type(value: str) -> None:
            wizard.body_type = value

        def _set_awd(value: str) -> None:
            wizard.needs_awd = value == "yes"

        def _set_fuel(value: str) -> None:
            wizard.fuel_pattern = value

        def _set_cargo(value: str) -> None:
            wizard.cargo_need = value

        def _set_priority(value: str) -> None:
            wizard.priority = value

        _content()

    def open_() -> None:
        """Opens the dialog and (re)renders it at the wizard's current step."""
        _content.refresh()
        dialog.open()

    return open_


def _footer(
    wizard: WizardState,
    refresh: Callable[[], None],
    on_skip: Callable[[], Awaitable[None]],
    on_next: Callable[[], Awaitable[None]] | None,
) -> None:
    """Renders the Back/Skip/Next row shared by every step.

    Args:
        wizard: Wizard state, to know whether a "Back" button is needed
            and whether this is the last step (changes the forward
            button's label).
        refresh: Re-renders the current step - called after Back.
        on_skip: Advances past the current step without recording an
            answer to it - this is `wizard_dialog`'s `_advance`, which on
            the last step finalizes and closes the dialog exactly like
            `on_next` would (there is nothing left to submit beyond what
            earlier steps already set).
        on_next: Reads the current step's input and advances. `None` for
            choice-button steps, which already advance on click and only
            need this footer for Back/Skip.
    """

    def _go_back() -> None:
        wizard.go_back()
        refresh()

    with ui.row().classes("mt-5 w-full items-center justify-between gap-2"):
        if wizard.step > 0:
            ui.button(t("wizard.back"), on_click=_go_back).props("flat no-caps").classes(
                "rounded-control border border-border px-3.5 py-2 text-[13px] text-subtext"
            )
        else:
            ui.element("div")

        with ui.row().classes("items-center gap-2"):
            ui.button(t("wizard.skip"), on_click=on_skip).props("flat no-caps").classes(
                "rounded-control border border-border px-3.5 py-2 text-[13px] text-subtext"
            )
            if on_next is not None:
                label = t("wizard.finish") if wizard.is_last_step else t("wizard.next")
                ui.button(label, on_click=on_next).props("no-caps unelevated").classes(
                    "rounded-control bg-accent px-4 py-2 text-[13px] font-semibold text-accent-text"
                )

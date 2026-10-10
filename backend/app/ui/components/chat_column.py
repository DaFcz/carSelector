"""Port of frontend/src/components/ChatColumn.tsx + ChatMessageBubble.tsx."""

from collections.abc import Awaitable, Callable

from nicegui import ui

from app.core.config import CHAT_MAX_MESSAGE_LENGTH
from app.ui.i18n import t
from app.ui.state import ConversationState


def _bubble(role: str, text: str) -> None:
    """Renders one chat message, right/accent for the user, left/muted for the assistant.

    Args:
        role: `"user"` or `"assistant"`.
        text: The message text.
    """
    is_user = role == "user"
    with ui.row().classes(f"w-full {'justify-end' if is_user else 'justify-start'}"):
        bubble_classes = "max-w-[82%] rounded-control border px-3.5 py-2.5 text-[13.5px] leading-relaxed " + (
            "border-accent bg-accent text-accent-text" if is_user else "border-border bg-ai-bubble text-text"
        )
        ui.label(text).classes(bubble_classes).style("white-space: pre-wrap")


def chat_column(state: ConversationState, on_send: Callable[[str], Awaitable[None]]) -> Callable[[], None]:
    """Builds the chat column: scrollable transcript + send form.

    Args:
        state: Conversation state to render messages/sending-indicator from.
        on_send: Called with the trimmed input text when the user submits
            (button click or Enter) - the caller (see `app/ui/pages.py`)
            is responsible for calling the returned refresh function
            afterward, since sending is async and this function itself
            can't await.

    Returns:
        A zero-argument function that re-renders the message list and
        input-disabled state from the current `state` - call after any
        mutation to `state`.
    """
    with ui.column().classes("flex w-full md:w-[400px] shrink-0 flex-col md:border-r border-border h-full gap-0"):
        scroll_area = ui.scroll_area().classes("min-h-0 grow")

        with scroll_area:

            @ui.refreshable
            def _messages() -> None:
                with ui.column().classes("gap-3.5 p-5 w-full"):
                    for role, text in state.messages:
                        _bubble(role, text)
                    if state.is_sending:
                        with ui.row().classes("w-full justify-start"):
                            ui.label(t("chat.sending")).classes(
                                "max-w-[82%] rounded-control border border-border bg-ai-bubble px-3.5 py-2.5 "
                                "text-[13.5px] italic text-subtext"
                            )

            _messages()

        with ui.row().classes("flex-nowrap gap-2 border-t border-border p-3 md:p-4 md:px-5 w-full items-center"):
            text_input = (
                ui.input(placeholder=t("chat.typePlaceholder"))
                .classes(
                    "min-w-0 grow rounded-full border border-border bg-ai-bubble px-4 py-2.5 text-[13px] text-text"
                )
                # Convenience only - the orchestrator enforces the limit.
                .props(
                    f"borderless dense maxlength={CHAT_MAX_MESSAGE_LENGTH}"
                    if CHAT_MAX_MESSAGE_LENGTH > 0
                    else "borderless dense"
                )
            )
            send_button = (
                ui.button(t("chat.send"), on_click=lambda: _submit())
                .props("no-caps unelevated")
                .classes("shrink-0 rounded-full bg-accent px-4 py-2.5 text-[13px] font-semibold text-accent-text")
            )

        async def _submit() -> None:
            draft = (text_input.value or "").strip()
            if not draft or state.is_sending:
                return
            text_input.value = ""
            await on_send(draft)

        text_input.on("keydown.enter", _submit)

    def refresh() -> None:
        """Re-renders the transcript and sync's the input/button disabled state with `state.is_sending`."""
        _messages.refresh()
        text_input.set_enabled(not state.is_sending)
        send_button.set_enabled(not state.is_sending)
        scroll_area.scroll_to(percent=1.0)

    return refresh

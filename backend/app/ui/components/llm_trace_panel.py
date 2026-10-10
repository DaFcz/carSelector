"""The admin console's "AI komunikace" tab: every LLM request/response
recorded by `app/ai/trace.py`, newest first, live-updating.

Admin-only by construction: built solely from `app/ui/admin.py`'s page,
after its `is_admin` check. Reads the process-wide `trace_log` directly
(in-memory, no I/O), so no `run.io_bound` is needed.

Entries render collapsed, and an entry's body (prompts, raw JSON) is only
built the first time it's opened - with a few hundred entries of multi-KB
prompts each, building every body up front would make each live refresh
ship megabytes to the browser.
"""

import json
from typing import Any

from nicegui import ui

from app.ai.trace import LlmTraceEntry, trace_log
from app.core import config
from app.ui.i18n import STRINGS, t

REFRESH_INTERVAL_SECONDS = 2.0

_SECTION_LABEL = "text-[11.5px] font-bold uppercase tracking-wide text-subtext"
_PRE = (
    "w-full whitespace-pre-wrap break-words rounded-control border border-border bg-panel-2 "
    "p-2.5 font-mono text-[11.5px] text-text"
)


def _purpose_label(purpose: str | None) -> str:
    """Czech label for a trace purpose; unknown keys fall back to the raw key.

    Args:
        purpose: `LlmTraceEntry.purpose`.
    """
    if purpose is None:
        return t("admin.trace.purposes.unknown")
    if purpose in STRINGS["admin"]["trace"]["purposes"]:
        return t(f"admin.trace.purposes.{purpose}")
    return purpose


def _caption(entry: LlmTraceEntry) -> str:
    """The one-line summary under an entry's title: status, latency, tokens.

    Args:
        entry: The entry to summarize.
    """
    status = t("admin.trace.ok") if entry.ok else t("admin.trace.failed", code=entry.error_code)
    if entry.input_tokens is None and entry.output_tokens is None:
        tokens = t("admin.trace.noUsage")
    else:
        tokens = t("admin.trace.tokens", input=entry.input_tokens or 0, output=entry.output_tokens or 0)
    return f"{status} · {entry.duration_ms:.0f} ms · {tokens}"


def _pretty_json(value: Any) -> str:
    """Indented JSON with Czech characters kept readable."""
    return json.dumps(value, indent=2, ensure_ascii=False, default=repr)


def _entry_body(entry: LlmTraceEntry) -> None:
    """Builds an opened entry's content: the conversation as sent, the
    reply or error, then both raw payloads.

    Args:
        entry: The entry to show.
    """
    with ui.column().classes("w-full gap-2.5"):
        if entry.error_message:
            ui.label(t("admin.trace.error")).classes(_SECTION_LABEL)
            ui.label(entry.error_message).classes(_PRE + " text-flag")

        ui.label(t("admin.trace.request")).classes(_SECTION_LABEL)
        # Anthropic carries the system prompt as its own parameter, Groq
        # as the first message - show both shapes the same way.
        messages = list(entry.request.get("messages", []))
        if "system" in entry.request:
            messages.insert(0, {"role": "system", "content": entry.request["system"]})
        for message in messages:
            ui.label(str(message.get("role", "?"))).classes("text-[11.5px] font-semibold text-accent")
            ui.label(str(message.get("content", ""))).classes(_PRE)

        if entry.ok:
            ui.label(t("admin.trace.reply")).classes(_SECTION_LABEL)
            ui.label(entry.reply_text or t("admin.trace.emptyReply")).classes(_PRE)

        ui.label(t("admin.trace.rawRequest")).classes(_SECTION_LABEL)
        ui.code(_pretty_json(entry.request), language="json").classes("w-full text-[11.5px]")
        ui.label(t("admin.trace.rawResponse")).classes(_SECTION_LABEL)
        ui.code(_pretty_json(entry.response), language="json").classes("w-full text-[11.5px]")


def _entry_row(entry: LlmTraceEntry, open_ids: set[int]) -> None:
    """One collapsible trace entry; remembers whether it's open across
    live refreshes via `open_ids`.

    Args:
        entry: The entry to render.
        open_ids: Ids of the entries this viewer currently has expanded.
    """
    title = (
        f"#{entry.id} · {entry.started_at.strftime('%d.%m. %H:%M:%S')} · "
        f"{_purpose_label(entry.purpose)} · {entry.provider}/{entry.model}"
    )
    is_open = entry.id in open_ids
    built = False

    def build() -> None:
        nonlocal built
        if built:
            return
        built = True
        with expansion:
            _entry_body(entry)

    def on_change(event: Any) -> None:
        if event.value:
            open_ids.add(entry.id)
            build()
        else:
            open_ids.discard(entry.id)

    expansion = ui.expansion(
        title,
        caption=_caption(entry),
        icon="check_circle" if entry.ok else "error",
        value=is_open,
        on_value_change=on_change,
    ).classes("w-full rounded-control border border-border bg-panel " + ("" if entry.ok else "border-flag"))
    if is_open:
        build()


def llm_trace_panel() -> None:
    """Builds the "AI komunikace" tab content: header with summary and
    controls, then the entry list, refreshed every
    `REFRESH_INTERVAL_SECONDS` while "Živě obnovovat" is on and something
    changed.
    """
    open_ids: set[int] = set()
    rendered_version = -1

    with ui.column().classes("w-full gap-3"):
        ui.label(t("admin.trace.title", provider=config.AI_PROVIDER)).classes("text-[15px] font-bold text-text")
        ui.label(t("admin.trace.description", max=trace_log.max_entries)).classes("text-[12.5px] text-subtext")
        if not trace_log.enabled:
            ui.label(t("admin.trace.disabled")).classes("text-[12.5px] font-semibold text-flag")
            return

        with ui.row().classes("w-full items-center gap-3"):
            summary = ui.label().classes("text-[12.5px] font-semibold text-text")
            ui.space()
            auto_refresh = ui.switch(t("admin.trace.autoRefresh"), value=True).classes("text-[12.5px]")
            ui.button(t("admin.trace.refresh"), icon="refresh", on_click=lambda: entries_list.refresh()).props(
                "no-caps flat"
            ).classes("rounded-control text-[13px] text-accent")
            ui.button(t("admin.trace.clear"), icon="delete_sweep", on_click=lambda: clear()).props(
                "no-caps flat"
            ).classes("rounded-control text-[13px] text-flag")

        @ui.refreshable
        def entries_list() -> None:
            nonlocal rendered_version
            rendered_version = trace_log.version
            entries = trace_log.entries()
            summary.set_text(
                t(
                    "admin.trace.summary",
                    count=len(entries),
                    errors=sum(1 for e in entries if not e.ok),
                    tokens=sum((e.input_tokens or 0) + (e.output_tokens or 0) for e in entries),
                )
            )
            if not entries:
                ui.label(t("admin.trace.empty")).classes("text-[12.5px] text-subtext")
                return
            with ui.column().classes("w-full gap-1.5"):
                for entry in entries:
                    _entry_row(entry, open_ids)

        def clear() -> None:
            trace_log.clear()
            open_ids.clear()
            entries_list.refresh()

        def poll() -> None:
            if auto_refresh.value and trace_log.version != rendered_version:
                entries_list.refresh()

        entries_list()
        ui.timer(REFRESH_INTERVAL_SECONDS, poll)

"""The admin console's "Porovnání" tab: the most compared car models, each
with the models it was most often compared with - see
`app/services/comparison_stats.py`. A period filter narrows it to the last
7/30/90 days.

Loaded only when the tab is first opened (see the returned `load`), not
with the rest of the console: the aggregation reads every recorded
comparison, which an admin opening the console for something else
shouldn't pay for.

Admin-only by construction: built solely from `app/ui/admin.py`'s page,
after its `is_admin` check; the service re-checks every read anyway.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from nicegui import ui

from app.schemas.comparison_stats import ComparedModelStat
from app.ui import comparison_stats_state
from app.ui.i18n import t, t_count

_ROW = "w-full rounded-control border border-border bg-panel px-3.5 py-2.5"
_FILTER = "min-w-[160px] rounded-control border border-border bg-panel-2 px-2.5 py-1 text-[13px] text-text"
# Period filter values: days back, "" = all time.
PERIODS = ("7", "30", "90", "")


@dataclass
class _Filters:
    period: str = "30"
    loaded: bool = False

    @property
    def since(self) -> datetime | None:
        return datetime.now(UTC) - timedelta(days=int(self.period)) if self.period else None


async def comparison_stats_admin_panel(admin_id: int) -> Callable[[], Awaitable[None]]:
    """Builds the tab, empty until the returned function loads it.

    Args:
        admin_id: The logged-in admin, passed to every service call.

    Returns:
        Loads the statistic on its first call; later calls do nothing
        (the period filter reloads it from then on).
    """
    filters = _Filters()

    async def set_period(value: str | None) -> None:
        filters.period = value or ""
        await content.refresh()

    @ui.refreshable
    async def content() -> None:
        if not filters.loaded:
            return
        outcome = await comparison_stats_state.most_compared(admin_id, filters.since)
        if not outcome.ok:
            ui.label(t(f"comparisonStats.errors.{outcome.error}")).classes("text-[13px] text-flag")
            return
        stats = outcome.value
        if not stats.models:
            ui.label(t("comparisonStats.empty")).classes("text-[13px] text-subtext")
            return
        ui.label(t_count("comparisonStats.total", stats.total)).classes("text-[12.5px] text-subtext").mark(
            "comparison-stats-total"
        )
        for rank, item in enumerate(stats.models, start=1):
            _model_row(rank, item)

    with ui.column().classes("w-full max-w-[860px] gap-3"):
        ui.label(t("comparisonStats.description")).classes("text-[12.5px] text-subtext")
        ui.select(
            {period: t(f"comparisonStats.periods.{period or 'all'}") for period in PERIODS},
            value=filters.period,
            on_change=lambda e: set_period(e.value),
        ).props("borderless dense options-dense").classes(_FILTER).mark("comparison-stats-period")
        with ui.column().classes("w-full gap-2"):
            await content()

    async def load() -> None:
        if filters.loaded:
            return
        filters.loaded = True
        await content.refresh()

    return load


def _model_row(rank: int, item: ComparedModelStat) -> None:
    """One compared model with its comparison partners.

    Args:
        rank: 1-based position in the list.
        item: The model's numbers.
    """
    with ui.column().classes(_ROW + " gap-2").mark("comparison-stats-row"):
        with ui.row().classes("w-full flex-nowrap items-baseline gap-2"):
            ui.label(f"{rank}.").classes("w-6 shrink-0 text-[13px] font-bold text-subtext")
            ui.label(f"{item.brand} {item.model}").classes("min-w-0 flex-1 text-[14px] font-bold text-text")
            ui.label(t_count("comparisonStats.comparisons", item.comparisons)).classes(
                "shrink-0 rounded-full bg-accent-soft px-2.5 py-0.5 text-[12px] font-semibold text-accent"
            )
        if item.within_model:
            ui.label(t_count("comparisonStats.withinModel", item.within_model)).classes(
                "pl-8 text-[11.5px] text-subtext"
            )
        if not item.partners:
            return
        ui.label(t("comparisonStats.partners")).classes(
            "pl-8 text-[11px] font-bold uppercase tracking-wide text-subtext"
        )
        with ui.column().classes("w-full gap-1 pl-8"):
            for partner in item.partners:
                share = round(100 * partner.count / item.comparisons) if item.comparisons else 0
                with ui.row().classes("w-full flex-nowrap items-center gap-2"):
                    ui.label(f"{partner.brand} {partner.model}").classes(
                        "w-[180px] shrink-0 truncate text-[12.5px] text-text"
                    )
                    with ui.element("div").classes("h-2 min-w-0 flex-1 overflow-hidden rounded-full bg-panel-2"):
                        ui.element("div").classes("h-full rounded-full bg-accent").style(f"width: {share}%")
                    ui.label(t("comparisonStats.partnerCount", count=partner.count, share=share)).classes(
                        "w-[90px] shrink-0 text-right text-[12px] text-subtext"
                    )

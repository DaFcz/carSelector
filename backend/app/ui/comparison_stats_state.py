"""UI-side calls into `app/services/comparison_stats.py` - each one a
`run.io_bound` around a short-lived session (see `app/ui/db.py`), like
`app/ui/feedback_state.py`'s.

`record` never fails the comparison it counts: a statistic is not worth an
error in front of the user, so anything unexpected is only logged.
"""

import logging
from datetime import datetime

from nicegui import run

from app.schemas.comparison_stats import ComparisonStats
from app.schemas.vehicle import VehicleDetail
from app.services import comparison_stats
from app.services.comparison_stats import ComparisonStatsError
from app.ui import db as ui_db
from app.ui.articles_state import Outcome

logger = logging.getLogger(__name__)


async def record(details: list[VehicleDetail]) -> None:
    """Counts one displayed comparison of `details` (see
    `comparison_stats.record`).

    Args:
        details: The compared cars.
    """
    model_ids = [detail.model_id for detail in details]

    def _run() -> None:
        with ui_db.get_session() as db:
            comparison_stats.record(db, model_ids)

    try:
        await run.io_bound(_run)
    except Exception:
        logger.exception("Recording a comparison failed")


async def most_compared(admin_id: int, since: datetime | None) -> Outcome[ComparisonStats]:
    """See `comparison_stats.most_compared`; refusals come back as the
    service's error code, anything unexpected as `"unknown_error"`."""

    def _run() -> ComparisonStats:
        with ui_db.get_session() as db:
            return comparison_stats.most_compared(db, admin_id, since)

    try:
        return Outcome(value=await run.io_bound(_run))
    except ComparisonStatsError as exc:
        return Outcome(error=exc.code)
    except Exception:
        logger.exception("Loading comparison statistics failed")
        return Outcome(error="unknown_error")

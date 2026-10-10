"""Deterministic filter + rank over the catalog. No AI here - the AI layer
(`app/ai`) only produces `StructuredRequirements` and, afterwards, per-result
explanations; this module owns retrieval and ordering, per the
drivewise-ai-recommendations skill's guardrail: "the AI never reads or ranks
the database directly."
"""

from collections.abc import Collection

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Brand, CarModel
from app.models.enums import FuelType
from app.schemas.requirement import StructuredRequirements
from app.schemas.vehicle import VehicleSummary
from app.services import catalog


class RecommendationEngine:
    """Filters the catalog on hard constraints, then scores and ranks the
    rest, per `drivewise-ai-recommendations`'s Code style section.
    Stateless (the scoring weights are fixed class constants, not
    per-instance config yet) - a single shared instance is fine (see the
    module-level `engine` singleton at the bottom of this file).
    """

    # Drivetrain is treated as a soft preference here, not a hard filter:
    # the scripted example this product is built around ("AWD for
    # mountain trips" -> "AWD optional for city commuting") explicitly
    # downgrades it to a nice-to-have mid-conversation, so excluding
    # non-matching drivetrains outright would wrongly drop viable cars.
    # `catalog.list_vehicles` still accepts drivetrain as a hard filter
    # for direct catalog browsing/search, where an explicit user filter
    # should behave like one.
    DRIVETRAIN_MATCH_WEIGHT = 20.0
    PRIORITY_MATCH_WEIGHT = 10.0
    BUDGET_HEADROOM_WEIGHT = 20.0
    # Liked models (the heart on a results card, see
    # app/services/liked_models.py) are a soft preference like drivetrain:
    # they reorder the hard-filtered matches, never add or remove any. The
    # brand bonus carries the taste over to other models of that brand, so
    # a liked model that the current requirements rule out (e.g. a liked
    # hatchback in an SUV search) still counts for something.
    LIKED_MODEL_WEIGHT = 15.0
    LIKED_BRAND_WEIGHT = 5.0
    BASE_SCORE = 50.0

    # The whole catalog is currently under 1,000 configurations (see
    # storage/README.md) - pulling every hard-filtered match here, rather
    # than capping at some arbitrary page, is what makes `_score` below a
    # true rank over ALL candidates instead of whichever ones happen to
    # come back first. A prior version capped this at 100 with no explicit
    # `sort`, which defaults `catalog.list_vehicles` to `configuration.id`
    # order - since ids are assigned in scrape/import order and Škoda was
    # the first brand ever imported, any budget filter narrow enough to
    # leave >=100 Škoda matches (Škoda alone has 186 configurations)
    # silently excluded every other brand from scoring entirely, no matter
    # how well they'd have matched (e.g. "just a 1,000,000 Kč budget, no
    # other requirements" returned Škoda-only results). `sort="price_asc"`
    # below is kept as a defensive fallback so that if the catalog outgrows
    # this cap, truncation degrades to "missing the priciest matches"
    # rather than reintroducing a single-brand monoculture.
    CANDIDATE_POOL_SIZE = 5000

    def _score(
        self,
        vehicle: VehicleSummary,
        requirements: StructuredRequirements,
        liked_model_ids: Collection[int] = (),
        liked_brands: Collection[str] = (),
    ) -> float:
        """Computes a soft-preference match score for one already
        hard-filtered candidate vehicle.

        Args:
            vehicle: A candidate that already passed the hard filters
                (body_type, budget, fuel_type) in `catalog.list_vehicles`.
            requirements: The structured requirements to score against.
            liked_model_ids: Models the user has liked.
            liked_brands: Brand names of those liked models.

        Returns:
            A score starting at `BASE_SCORE`, increased for a matching
            drivetrain, each matched priority, budget headroom (more
            headroom scores higher, capped by `BUDGET_HEADROOM_WEIGHT`),
            and a liked model (`LIKED_MODEL_WEIGHT`) or, failing that, a
            liked model's brand (`LIKED_BRAND_WEIGHT`). Not bounded to any
            fixed range beyond that.
        """
        score = self.BASE_SCORE

        if requirements.drivetrain is not None and requirements.drivetrain.value.upper() in vehicle.specs:
            score += self.DRIVETRAIN_MATCH_WEIGHT

        for priority in requirements.priorities:
            if any(priority.lower() in tag.lower() for tag in vehicle.specs):
                score += self.PRIORITY_MATCH_WEIGHT

        if requirements.budget_max is not None and vehicle.price.currency == requirements.budget_max.currency:
            # Reward comfortably-under-budget over barely-under-budget.
            headroom = (requirements.budget_max.amount - vehicle.price.amount) / requirements.budget_max.amount
            score += max(0.0, headroom) * self.BUDGET_HEADROOM_WEIGHT

        if vehicle.model_id in liked_model_ids:
            score += self.LIKED_MODEL_WEIGHT
        elif vehicle.brand in liked_brands:
            score += self.LIKED_BRAND_WEIGHT

        return score

    def recommend(
        self,
        db: Session,
        requirements: StructuredRequirements,
        *,
        market: str = catalog.DEFAULT_MARKET,
        limit: int | None = None,
        liked_model_ids: Collection[int] = (),
    ) -> list[VehicleSummary]:
        """Filters the catalog on hard constraints, then scores and ranks
        the rest.

        Hard constraints: body_type, budget, fuel_type (hard-filtered via
        `catalog.list_vehicles`). Soft preferences: drivetrain,
        priorities, budget headroom, liked models and their brands (scored
        by `_score`). `min_seats` is
        accepted on the contract's `StructuredRequirements` but has no
        backing data yet - see `catalog.list_vehicles`'s docstring - so
        it's a no-op here too.

        `flag` (e.g. "Over budget by ~2,200 Kc") from the design concept
        is intentionally not populated: that behavior means relaxing the
        budget filter and including some over-budget results anyway,
        which is a product decision this pass doesn't make. Budget stays
        a strict hard filter for now.

        Args:
            db: Database session to query the catalog through.
            requirements: Structured output of the AI requirement
                interpreter (or a direct caller building one manually).
            market: Market to price and filter against.
            limit: Maximum number of ranked results to return, or `None`
                (the default) for every hard-filtered match. A hard
                constraint like budget isn't something to additionally
                truncate on top of - a user who set a 1,000,000 Kč budget
                and nothing else expects every match under it, not an
                arbitrary top-N (reported: a budget-only wizard answer
                returning just 10 of the 462 actual matches). Callers that
                need a bounded shortlist for a different reason (e.g.
                `ConversationOrchestrator` capping how many results get an
                AI-generated explanation, not how many are returned to the
                user) should truncate on their own end instead of asking
                this method to hide genuine matches.
            liked_model_ids: Models the user has liked (see
                `app/services/liked_models.py`) - boosts their ranking,
                never filters.

        Returns:
            Vehicles ranked best-first (highest score to lowest), each
            with `match_score` set to the rounded score capped at 100,
            and the top result (if any) flagged `top_pick=True`.
        """
        fuel_type = None
        if requirements.fuel_type:
            try:
                fuel_type = FuelType(requirements.fuel_type)
            except ValueError:
                fuel_type = None

        candidates = catalog.list_vehicles(
            db,
            body_type=requirements.body_type,
            fuel_type=fuel_type,
            budget_max=requirements.budget_max.amount if requirements.budget_max else None,
            currency=requirements.budget_max.currency if requirements.budget_max else "CZK",
            market=market,
            sort="price_asc",
            page=1,
            page_size=self.CANDIDATE_POOL_SIZE,
        ).items

        liked_brands: set[str] = set()
        if liked_model_ids:
            liked_brands = set(
                db.scalars(
                    select(Brand.name)
                    .join(CarModel, CarModel.brand_id == Brand.id)
                    .where(CarModel.id.in_(list(liked_model_ids)))
                )
            )

        scored = sorted(
            ((self._score(vehicle, requirements, liked_model_ids, liked_brands), vehicle) for vehicle in candidates),
            key=lambda pair: pair[0],
            reverse=True,
        )[:limit]

        results = [vehicle.model_copy(update={"match_score": min(round(score), 100)}) for score, vehicle in scored]
        if results:
            results[0] = results[0].model_copy(update={"top_pick": True})
        return results


# Shared instance for callers that don't need a custom configuration -
# construction here does no I/O, so a fresh instance would be just as
# cheap, but a shared one keeps the "one engine" mental model consistent
# with the AI-layer singletons in app/ai/.
engine = RecommendationEngine()

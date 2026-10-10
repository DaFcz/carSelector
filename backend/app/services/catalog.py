"""Read queries backing the catalog endpoints (brands / models / vehicles).

Deliberately plain SQLAlchemy queries, not a generic repository abstraction -
there are only 5 read shapes and they don't share enough to be worth
hiding behind an interface yet.
"""

from collections.abc import Collection

from sqlalchemy import and_, case, func, select
from sqlalchemy.orm import Session, joinedload

from app.models import (
    Brand,
    CarModel,
    Color,
    Configuration,
    ConfigurationColor,
    OptionAvailability,
    OptionItem,
    Powertrain,
    Price,
    Trim,
)
from app.models.enums import AvailabilityStatus, Drivetrain, FuelType
from app.schemas.catalog import BrandRead, ModelOverview, TrimChoice, TrimOverview
from app.schemas.common import Money, Page
from app.schemas.vehicle import (
    ColorOption,
    OptionLine,
    PowertrainSpec,
    PricePoint,
    VehicleDetail,
    VehicleSummary,
)

DEFAULT_MARKET = "CZ"

_SUMMARY_LOAD_OPTIONS = (
    joinedload(Configuration.trim).joinedload(Trim.model).joinedload(CarModel.brand),
    joinedload(Configuration.powertrain),
)


def _build_powertrain_spec(powertrain: Powertrain) -> PowertrainSpec:
    """Args:
        powertrain: ORM row to project onto the API's `PowertrainSpec` shape.

    Returns:
        The subset of `powertrain`'s fields the API contract exposes.
    """
    return PowertrainSpec(
        fuel_type=powertrain.fuel_type,
        transmission=powertrain.transmission,
        drivetrain=powertrain.drivetrain,
        power_kw=powertrain.power_kw,
        power_hp=powertrain.power_hp,
        consumption_min=powertrain.consumption_min,
        consumption_max=powertrain.consumption_max,
        consumption_unit=powertrain.consumption_unit,
        co2_min_g_km=powertrain.co2_min_g_km,
        co2_max_g_km=powertrain.co2_max_g_km,
    )


def _build_specs_tags(powertrain: Powertrain) -> list[str]:
    """Args:
        powertrain: ORM row to derive display tags from.

    Returns:
        Short display tags for a vehicle card, e.g. `["AWD", "Hybrid"]`.
        Simplified placeholder: the source price lists never state seat
        count (see doc/api-contract.md "open items"), so this can't yet
        match the richer ["AWD", "5 seats", "Hybrid"]-style tags from the
        original design concept - only powertrain-derived tags for now.
    """
    tags = [powertrain.drivetrain.value.upper()]
    if powertrain.fuel_type != FuelType.petrol:
        tags.append(powertrain.fuel_type.value.replace("_", " ").title())
    return tags


def _build_vehicle_summary(configuration: Configuration, price: Price) -> VehicleSummary:
    """Args:
        configuration: ORM row with `trim`/`powertrain` eagerly loaded
            (via `_SUMMARY_LOAD_OPTIONS`) - accessing them here must not
            trigger a lazy-load query.
        price: The configuration's current price row (`valid_to IS NULL`)
            for the market being queried.

    Returns:
        The recommendation-card/results-grid shape for this configuration,
        per doc/api-contract.md's `VehicleSummary`.
    """
    trim = configuration.trim
    model = trim.model
    return VehicleSummary(
        configuration_id=configuration.id,
        model_id=model.id,
        brand=model.brand.name,
        model=model.name,
        trim=trim.name,
        price=Money(amount=float(price.price_incl_vat), currency=price.currency),
        specs=_build_specs_tags(configuration.powertrain),
    )


_SORT_ORDER_BY = {
    "price_asc": (Price.price_incl_vat.asc(),),
    "price_desc": (Price.price_incl_vat.desc(),),
    "alpha": (Brand.name.asc(), CarModel.name.asc(), Trim.name.asc()),
}


def list_vehicles(
    db: Session,
    *,
    brand_id: int | None = None,
    body_type: str | None = None,
    fuel_type: FuelType | None = None,
    drivetrain: Drivetrain | None = None,
    budget_max: float | None = None,
    currency: str = "CZK",
    market: str = DEFAULT_MARKET,
    sort: str | None = None,
    preferred_model_ids: Collection[int] = (),
    page: int = 1,
    page_size: int = 20,
) -> Page[VehicleSummary]:
    """Catalog browse/search, independent of the chat flow.

    `min_seats` from the API contract is intentionally not a parameter
    here yet: the source data has no seat-count field anywhere in the
    schema, so accepting the param and silently ignoring it would be
    worse than not accepting it at all.

    Args:
        db: Database session to query through.
        brand_id: Hard filter on `brands.id`, if given.
        body_type: Exact-match filter on `models.category`, if given.
        fuel_type: Hard filter on `powertrains.fuel_type`, if given.
        drivetrain: Hard filter on `powertrains.drivetrain`, if given -
            for direct catalog browsing; the recommendation engine treats
            drivetrain as a soft preference instead, see
            `drivewise-ai-recommendations`.
        budget_max: Hard filter, `price_incl_vat <= budget_max`, if given
            (compared only against rows in `currency`).
        currency: Currency `budget_max` is denominated in.
        market: Market to price and filter against.
        sort: One of `"price_asc"`, `"price_desc"`, `"alpha"` (brand, then
            model, then trim), or `None` for the default order
            (`configurations.id`). Only orderings the frontend's paginated
            "load more" flow needs live here - anything the client already
            has the full page for (e.g. the AI-narrowed shortlist) sorts
            client-side instead, see `frontend/src/utils/sortCars.ts`.
        preferred_model_ids: Models to list first in the default order
            (`sort=None`) - the user's liked models (see
            `app/services/liked_models.py`), so browsing puts them on
            the first page. Ignored by the explicit sorts, which the user
            picked on purpose. Never filters anything out.
        page: 1-indexed page number.
        page_size: Rows per page.

    Returns:
        A `Page[VehicleSummary]` with `items` for the requested page and
        `total` set to the full matching count (not just this page's size).
    """
    current_price_join = and_(
        Price.configuration_id == Configuration.id,
        Price.market == market,
        Price.valid_to.is_(None),
    )

    stmt = (
        select(Configuration, Price)
        .join(Trim, Configuration.trim_id == Trim.id)
        .join(CarModel, Trim.model_id == CarModel.id)
        .join(Brand, CarModel.brand_id == Brand.id)
        .join(Powertrain, Configuration.powertrain_id == Powertrain.id)
        .join(Price, current_price_join)
        .options(*_SUMMARY_LOAD_OPTIONS)
    )
    if brand_id is not None:
        stmt = stmt.where(Brand.id == brand_id)
    if body_type:
        stmt = stmt.where(CarModel.category == body_type)
    if fuel_type:
        stmt = stmt.where(Powertrain.fuel_type == fuel_type)
    if drivetrain:
        stmt = stmt.where(Powertrain.drivetrain == drivetrain)
    if budget_max is not None:
        stmt = stmt.where(Price.currency == currency, Price.price_incl_vat <= budget_max)

    total = db.scalar(select(func.count()).select_from(stmt.with_only_columns(Configuration.id).subquery()))

    order_by = _SORT_ORDER_BY.get(sort, (Configuration.id.asc(),))
    if sort not in _SORT_ORDER_BY and preferred_model_ids:
        order_by = (case((CarModel.id.in_(list(preferred_model_ids)), 0), else_=1), *order_by)
    stmt = stmt.order_by(*order_by).offset((page - 1) * page_size).limit(page_size)
    rows = db.execute(stmt).unique().all()

    items = [_build_vehicle_summary(configuration, price) for configuration, price in rows]
    return Page(items=items, page=page, page_size=page_size, total=total or 0)


def get_vehicle_detail(db: Session, configuration_id: int, *, market: str = DEFAULT_MARKET) -> VehicleDetail | None:
    """Full detail page for one configuration: summary + powertrain spec,
    colors, standard/optional equipment, and price history.

    Args:
        db: Database session to query through.
        configuration_id: Id of the `configurations` row to fetch.
        market: Market to price against - also determines which price row
            counts as "current" (`valid_to IS NULL` for this market).

    Returns:
        The full detail, or `None` if `configuration_id` doesn't exist or
        has no current price row for `market`.
    """
    configuration = (
        db.execute(select(Configuration).where(Configuration.id == configuration_id).options(*_SUMMARY_LOAD_OPTIONS))
        .unique()
        .scalar_one_or_none()
    )
    if configuration is None:
        return None

    price = db.execute(
        select(Price).where(
            Price.configuration_id == configuration_id,
            Price.market == market,
            Price.valid_to.is_(None),
        )
    ).scalar_one_or_none()
    if price is None:
        return None

    summary = _build_vehicle_summary(configuration, price)

    color_rows = db.execute(
        select(ConfigurationColor, Color)
        .join(Color, ConfigurationColor.color_id == Color.id)
        .where(ConfigurationColor.configuration_id == configuration_id)
    ).all()
    colors = [
        ColorOption(
            name=color.name,
            finish_type=color.finish_type,
            surcharge=Money(amount=float(cc.surcharge_amount), currency=cc.currency),
        )
        for cc, color in color_rows
    ]

    option_rows = db.execute(
        select(OptionAvailability, OptionItem)
        .join(OptionItem, OptionAvailability.option_item_id == OptionItem.id)
        .where(OptionAvailability.configuration_id == configuration_id)
    ).all()
    standard_equipment = [
        item.name for availability, item in option_rows if availability.availability == AvailabilityStatus.standard
    ]
    optional_equipment = [
        OptionLine(
            name=item.name,
            category=item.category,
            surcharge=Money(amount=float(availability.surcharge_amount), currency=availability.currency),
        )
        for availability, item in option_rows
        if availability.availability == AvailabilityStatus.optional
    ]

    price_history_rows = (
        db.execute(
            select(Price)
            .where(Price.configuration_id == configuration_id, Price.market == market)
            .order_by(Price.valid_from)
        )
        .scalars()
        .all()
    )
    price_history = [
        PricePoint(
            valid_from=p.valid_from,
            valid_to=p.valid_to,
            price=Money(amount=float(p.price_incl_vat), currency=p.currency),
            lowest_price_30d=(
                Money(amount=float(p.lowest_price_30d), currency=p.currency) if p.lowest_price_30d is not None else None
            ),
        )
        for p in price_history_rows
    ]

    return VehicleDetail(
        **summary.model_dump(),
        powertrain=_build_powertrain_spec(configuration.powertrain),
        colors=colors,
        standard_equipment=standard_equipment,
        optional_equipment=optional_equipment,
        price_history=price_history,
    )


def compare_vehicles(
    db: Session, configuration_ids: list[int], *, market: str = DEFAULT_MARKET
) -> tuple[list[VehicleDetail], list[int]]:
    """Looks up full detail for each id in `configuration_ids`.

    Args:
        db: Database session to query through.
        configuration_ids: Configuration ids to fetch detail for, 2-4 per
            doc/api-contract.md - not enforced here, the router validates
            the count before calling this.
        market: Market to price each vehicle against.

    Returns:
        `(found, missing_ids)` - `found` is full detail for every id that
        resolved to a priced configuration, `missing_ids` is the ids that
        didn't (unknown id, or no current price for `market`); the router
        decides how to report `missing_ids` (a 404).
    """
    found: list[VehicleDetail] = []
    missing: list[int] = []
    for configuration_id in configuration_ids:
        detail = get_vehicle_detail(db, configuration_id, market=market)
        if detail is None:
            missing.append(configuration_id)
        else:
            found.append(detail)
    return found, missing


def list_trim_alternatives(db: Session, configuration_id: int, *, market: str = DEFAULT_MARKET) -> list[TrimChoice]:
    """Every priced trim of `configuration_id`'s model, each represented by
    one configuration - for comparing a model's trims ("flavours") side by
    side. The configuration's own trim is represented by the configuration
    itself; every other trim by its configuration with the same powertrain
    when it offers one (so only the equipment differs), else by its
    cheapest configuration.

    Args:
        db: Database session to query through.
        configuration_id: The configuration the comparison starts from.
        market: Market to price against; trims with no priced
            configuration in it are left out.

    Returns:
        One choice per trim, in the model's trim display order - empty if
        `configuration_id` doesn't exist.
    """
    origin = db.execute(
        select(Configuration).where(Configuration.id == configuration_id).options(joinedload(Configuration.trim))
    ).scalar_one_or_none()
    if origin is None:
        return []

    current_price_join = and_(
        Price.configuration_id == Configuration.id,
        Price.market == market,
        Price.valid_to.is_(None),
    )
    rows = (
        db.execute(
            select(Configuration, Price)
            .join(Price, current_price_join)
            .join(Trim, Trim.id == Configuration.trim_id)
            .where(Trim.model_id == origin.trim.model_id)
            .options(*_SUMMARY_LOAD_OPTIONS)
        )
        .unique()
        .all()
    )

    by_trim: dict[int, list[tuple[Configuration, Price]]] = {}
    for configuration, price in rows:
        by_trim.setdefault(configuration.trim_id, []).append((configuration, price))

    choices: list[tuple[Trim, TrimChoice]] = []
    for trim_rows in by_trim.values():
        trim = trim_rows[0][0].trim
        is_current = trim.id == origin.trim_id
        same_engine = [row for row in trim_rows if row[0].powertrain_id == origin.powertrain_id]
        if is_current:
            pool = [row for row in trim_rows if row[0].id == origin.id] or same_engine or trim_rows
        else:
            pool = same_engine or trim_rows
        configuration, price = min(pool, key=lambda row: row[1].price_incl_vat)
        choices.append(
            (
                trim,
                TrimChoice(
                    trim_id=trim.id,
                    trim_name=trim.name,
                    vehicle=_build_vehicle_summary(configuration, price),
                    same_engine=configuration.powertrain_id == origin.powertrain_id,
                    is_current=is_current,
                ),
            )
        )
    # Imported trims may have no display order - those go last, cheapest
    # first (trims usually step up in price), then by name.
    choices.sort(
        key=lambda pair: (
            pair[0].display_order is None,
            pair[0].display_order or 0,
            pair[1].vehicle.price.amount,
            pair[0].name,
        )
    )
    return [choice for _, choice in choices]


def list_brands(db: Session) -> list[BrandRead]:
    """Args:
        db: Database session to query through.

    Returns:
        Every brand in the catalog, alphabetical by name.
    """
    brands = db.execute(select(Brand).order_by(Brand.name)).scalars().all()
    return [BrandRead(id=b.id, name=b.name, slug=b.slug) for b in brands]


def get_model_overview(db: Session, model_id: int, *, market: str = DEFAULT_MARKET) -> ModelOverview | None:
    """One model's trims, each with its available (priced) configurations
    - the shape a model/vehicle-family landing page would use.

    Args:
        db: Database session to query through.
        model_id: Id of the `models` row to fetch.
        market: Market to price configurations against; a configuration
            with no current price row for `market` is left out of its
            trim's `configurations` list.

    Returns:
        The overview, or `None` if `model_id` doesn't exist.
    """
    model = (
        db.execute(select(CarModel).where(CarModel.id == model_id).options(joinedload(CarModel.brand)))
        .unique()
        .scalar_one_or_none()
    )
    if model is None:
        return None

    trims = (
        db.execute(select(Trim).where(Trim.model_id == model_id).order_by(Trim.display_order, Trim.name))
        .scalars()
        .all()
    )

    current_price_join = and_(
        Price.configuration_id == Configuration.id,
        Price.market == market,
        Price.valid_to.is_(None),
    )

    trim_overviews = []
    for trim in trims:
        rows = (
            db.execute(
                select(Configuration, Price)
                .join(Price, current_price_join)
                .where(Configuration.trim_id == trim.id)
                .options(*_SUMMARY_LOAD_OPTIONS)
            )
            .unique()
            .all()
        )
        configurations = [_build_vehicle_summary(configuration, price) for configuration, price in rows]
        trim_overviews.append(TrimOverview(id=trim.id, name=trim.name, configurations=configurations))

    return ModelOverview(
        brand=model.brand.name,
        model=model.name,
        category=model.category,
        trims=trim_overviews,
    )

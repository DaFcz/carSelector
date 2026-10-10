"""Regression test for a candidate-pool truncation bug: `recommend()` used
to cap `catalog.list_vehicles` at page_size=100 with no explicit `sort`,
which defaults to `configuration.id` ascending. Since ids are assigned in
scrape/import order, a budget filter narrow enough to leave >=100 matches
from whichever brand was imported first (Škoda, in production - see
`RecommendationEngine.CANDIDATE_POOL_SIZE`'s own comment) silently excluded
every other brand from scoring entirely, no matter how well - or how much
more cheaply - they'd have matched. Reproduced here with a synthetic
catalog: brand "AAA" gets the low ids (inserted first, like Škoda always
being scraped/imported first in production) but is pricier than brand
"ZZZ" (inserted second, higher ids) - the exact shape that broke."""
from datetime import UTC, date, datetime

from sqlalchemy.orm import Session

from app.models import Brand, CarModel, Configuration, Powertrain, Price, SourceDocument, Trim
from app.models.enums import DocumentType, Drivetrain, FuelType
from app.schemas.common import Money
from app.schemas.requirement import StructuredRequirements
from app.services.recommendation_engine import RecommendationEngine


def _add_catalog(session: Session, brand_slug: str, brand_name: str, count: int, price: int, id_offset: int) -> None:
    brand = Brand(id=id_offset, slug=brand_slug, name=brand_name)
    session.add(brand)
    session.flush()

    model = CarModel(id=id_offset, brand_id=brand.id, slug=f"{brand_slug}-model", name="Model", category="SUV")
    session.add(model)
    session.flush()

    source_doc = SourceDocument(
        id=id_offset,
        model_id=model.id,
        file_path=f"storage/cars/{brand_slug}/pricelist.pdf",
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
            id=row_id,
            model_id=model.id,
            fuel_type=FuelType.petrol,
            transmission="automatic",
            drivetrain=Drivetrain.fwd,
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
                list_price=price,
                price_incl_vat=price,
                valid_from=date(2026, 1, 1),
                valid_to=None,
                scraped_at=datetime.now(UTC),
            )
        )
    session.commit()


def test_recommend_does_not_let_a_low_id_brand_crowd_out_a_cheaper_one(db_session: Session) -> None:
    # "AAA" is inserted first (low ids, like Škoda always being
    # imported/scraped first in production) with MORE matches (105) than
    # the old hardcoded page_size=100 could hold, but at a HIGHER price
    # than "ZZZ" (inserted second, higher ids, far fewer matches). Both are
    # well within budget - this reproduces the exact production shape
    # (Škoda: 186 sub-1M matches, every other brand's ids come after it).
    _add_catalog(db_session, "aaa", "AAA", count=105, price=500_000, id_offset=1)
    _add_catalog(db_session, "zzz", "ZZZ", count=2, price=100_000, id_offset=1000)

    engine = RecommendationEngine()
    engine.CANDIDATE_POOL_SIZE = 5  # exercise the fix's own truncation path without inserting thousands of rows

    results = engine.recommend(
        db_session,
        StructuredRequirements(budget_max=Money(amount=600_000, currency="CZK")),
        limit=10,
    )

    brands = {vehicle.brand for vehicle in results}
    assert "ZZZ" in brands  # the cheaper, higher-id brand must not be silently excluded
    # ZZZ is strictly cheaper than AAA, so it must rank ahead of every AAA result.
    zzz_scores = {v.match_score for v in results if v.brand == "ZZZ"}
    aaa_scores = {v.match_score for v in results if v.brand == "AAA"}
    assert min(zzz_scores) >= max(aaa_scores)


def test_recommend_returns_every_hard_filtered_match_by_default(db_session: Session) -> None:
    # A hard constraint (budget) isn't something to additionally truncate
    # on top of - reported: a wizard answer with only a 1,000,000 Kč budget
    # returned just 10 of the real, much larger set of matches. 37 > the
    # old hardcoded limit=10 default.
    _add_catalog(db_session, "aaa", "AAA", count=37, price=500_000, id_offset=1)

    engine = RecommendationEngine()
    results = engine.recommend(
        db_session,
        StructuredRequirements(budget_max=Money(amount=600_000, currency="CZK")),
    )

    assert len(results) == 37

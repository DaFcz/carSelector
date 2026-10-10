from datetime import UTC, date, datetime

import pytest
from sqlalchemy.orm import Session

from app.models import Brand, CarModel, Configuration, Powertrain, Price, SourceDocument, Trim
from app.models.enums import DocumentType, Drivetrain, FuelType
from app.models.liked_model import LikedModel
from app.models.user import User
from app.schemas.requirement import StructuredRequirements
from app.services import catalog, liked_models
from app.services.recommendation_engine import RecommendationEngine
from tests.conftest import SeededData


def _user(session: Session, email: str = "driver@example.cz") -> User:
    row = User(email=email, is_admin=False, is_active=True, created_at=datetime.now(UTC))
    session.add(row)
    session.commit()
    return row


@pytest.fixture()
def user(seeded_session: SeededData) -> User:
    return _user(seeded_session.session)


def test_nothing_liked_by_default(seeded_session: SeededData, user: User) -> None:
    assert liked_models.list_ids(seeded_session.session, user.id) == set()


def test_like_then_unlike_round_trips(seeded_session: SeededData, user: User) -> None:
    db = seeded_session.session

    liked_models.like(db, user.id, seeded_session.vw_model_id)
    assert liked_models.list_ids(db, user.id) == {seeded_session.vw_model_id}

    liked_models.unlike(db, user.id, seeded_session.vw_model_id)
    assert liked_models.list_ids(db, user.id) == set()


def test_liking_twice_keeps_one_row(seeded_session: SeededData, user: User) -> None:
    db = seeded_session.session

    liked_models.like(db, user.id, seeded_session.model_id)
    liked_models.like_many(db, user.id, [seeded_session.model_id, seeded_session.vw_model_id])

    assert liked_models.list_ids(db, user.id) == {seeded_session.model_id, seeded_session.vw_model_id}
    assert db.query(LikedModel).filter(LikedModel.user_id == user.id).count() == 2


def test_likes_are_scoped_per_user(seeded_session: SeededData, user: User) -> None:
    other = _user(seeded_session.session, "other@example.cz")

    liked_models.like(seeded_session.session, user.id, seeded_session.vw_model_id)

    assert liked_models.list_ids(seeded_session.session, other.id) == set()


def test_unliking_a_model_that_was_not_liked_is_a_no_op(seeded_session: SeededData, user: User) -> None:
    liked_models.unlike(seeded_session.session, user.id, seeded_session.vw_model_id)

    assert liked_models.list_ids(seeded_session.session, user.id) == set()


# --- how likes affect search ---------------------------------------------


def test_liked_model_ranks_first_in_recommendations(seeded_session: SeededData) -> None:
    # No requirements: every seeded car scores the same base, so without a
    # like the order is just price. The like alone must lift the VW above
    # the (cheaper) Mazda.
    engine = RecommendationEngine()
    baseline = engine.recommend(seeded_session.session, StructuredRequirements())
    assert baseline[0].model_id == seeded_session.model_id

    results = engine.recommend(
        seeded_session.session, StructuredRequirements(), liked_model_ids={seeded_session.vw_model_id}
    )

    assert {car.model_id for car in results[:2]} == {seeded_session.vw_model_id}
    assert results[0].top_pick


def test_likes_rank_but_never_filter(seeded_session: SeededData) -> None:
    engine = RecommendationEngine()

    without = engine.recommend(seeded_session.session, StructuredRequirements())
    with_like = engine.recommend(
        seeded_session.session, StructuredRequirements(), liked_model_ids={seeded_session.vw_model_id}
    )

    assert {car.configuration_id for car in with_like} == {car.configuration_id for car in without}


def _add_model(session: Session, brand_id: int, model_id: int, price: int) -> None:
    """One extra model with a single configuration, for the brand-affinity case."""
    session.add(CarModel(id=model_id, brand_id=brand_id, slug=f"extra-{model_id}", name=f"Extra {model_id}"))
    session.add(
        SourceDocument(
            id=model_id,
            model_id=model_id,
            file_path=f"storage/cars/extra-{model_id}.pdf",
            document_type=DocumentType.price_list,
            market="CZ",
            locale="cs-CZ",
            effective_date=date(2026, 1, 1),
            retrieved_at=datetime.now(UTC),
        )
    )
    session.add(Trim(id=model_id, model_id=model_id, name="Base", display_order=1))
    session.add(
        Powertrain(
            id=model_id, model_id=model_id, fuel_type=FuelType.petrol, transmission="manual", drivetrain=Drivetrain.fwd
        )
    )
    session.flush()
    session.add(Configuration(id=model_id, trim_id=model_id, powertrain_id=model_id))
    session.flush()
    session.add(
        Price(
            id=model_id,
            configuration_id=model_id,
            source_document_id=model_id,
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


def test_liked_models_brand_gets_a_smaller_boost(db_session: Session) -> None:
    db_session.add_all([Brand(id=1, slug="aaa", name="AAA"), Brand(id=2, slug="zzz", name="ZZZ")])
    db_session.commit()
    _add_model(db_session, brand_id=1, model_id=10, price=500_000)  # the liked model
    _add_model(db_session, brand_id=1, model_id=11, price=500_000)  # same brand, not liked
    _add_model(db_session, brand_id=2, model_id=20, price=500_000)  # other brand

    results = RecommendationEngine().recommend(db_session, StructuredRequirements(), liked_model_ids={10})

    assert [car.model_id for car in results] == [10, 11, 20]
    scores = [car.match_score for car in results]
    assert scores[0] > scores[1] > scores[2]


def test_catalog_lists_liked_models_first_in_default_order(seeded_session: SeededData) -> None:
    page = catalog.list_vehicles(seeded_session.session, preferred_model_ids={seeded_session.vw_model_id})

    assert [car.model_id for car in page.items[:2]] == [seeded_session.vw_model_id] * 2
    assert page.total == 4  # reordered, nothing dropped


def test_catalog_explicit_sort_ignores_likes(seeded_session: SeededData) -> None:
    plain = catalog.list_vehicles(seeded_session.session, sort="price_asc")
    liked = catalog.list_vehicles(
        seeded_session.session, sort="price_asc", preferred_model_ids={seeded_session.vw_model_id}
    )

    assert [car.configuration_id for car in liked.items] == [car.configuration_id for car in plain.items]

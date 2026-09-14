from dataclasses import dataclass

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_db
from app.db.base import Base
from app.db.seed import seed_demo_data
from app.main import app


@dataclass
class SeededData:
    session: Session
    model_id: int
    config_prime_2wd_id: int
    config_centre_awd_id: int
    vw_model_id: int
    config_people_fwd_id: int
    config_rline_awd_id: int


@pytest.fixture()
def db_session():
    # SQLite renders our Postgres-native Enum columns as VARCHAR+CHECK,
    # which is enough to exercise the ORM/API layer end to end without a
    # live Postgres instance (see backend/README.md for why the first
    # migration was verified the same way).
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def seeded_session(db_session: Session) -> SeededData:
    data = seed_demo_data(db_session)
    return SeededData(
        session=db_session,
        model_id=data.model_id,
        config_prime_2wd_id=data.config_prime_2wd_id,
        config_centre_awd_id=data.config_centre_awd_id,
        vw_model_id=data.vw_model_id,
        config_people_fwd_id=data.config_people_fwd_id,
        config_rline_awd_id=data.config_rline_awd_id,
    )


@pytest.fixture()
def client(seeded_session: SeededData) -> TestClient:
    def _override_get_db():
        yield seeded_session.session

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()

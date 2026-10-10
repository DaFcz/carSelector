"""DB connection. SQLite locally (no Docker/Postgres setup to start),
once the pipeline is verified it switches to Postgres via the same
SQLAlchemy models (see doc/arch/webScraping/IMPLEMENTATION_PLAN.md,
the transition phase)."""

from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from scraper.database.models import Base

# Repo-root storage/scraper.db, not scraper/storage/scraper.db - see
# downloaders/pdf_downloader.py's STORAGE_ROOT and storage/README.md.
DEFAULT_SQLITE_PATH = Path(__file__).resolve().parents[2] / "storage" / "scraper.db"
DATABASE_URL = os.environ.get("SCRAPER_DATABASE_URL", f"sqlite:///{DEFAULT_SQLITE_PATH}")

engine = create_engine(DATABASE_URL, echo=False)
SessionLocal = sessionmaker(bind=engine)


def init_db() -> None:
    Base.metadata.create_all(engine)


def get_session() -> Session:
    return SessionLocal()

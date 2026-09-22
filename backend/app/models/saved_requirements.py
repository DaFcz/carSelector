from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, BigIntPK


class SavedRequirements(Base):
    """A logged-in user's most recent `StructuredRequirements` snapshot
    (see `app/schemas/requirement.py`), serialized as JSON.

    `app/services/conversation.py`'s conversation state is purely
    in-memory, keyed by a `conversation_id` a page load throws away and
    replaces with a fresh one - so without this, the "Technické
    požadavky" drawer always started empty again after a reload or a new
    login session. One row per user (`user_id` unique): a new save
    overwrites the previous one rather than keeping history, since there
    is no UI for browsing past snapshots, only "what I had last time" -
    see `app/services/saved_requirements.py`.
    """

    __tablename__ = "saved_requirements"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True, nullable=False)
    # StructuredRequirements.model_dump_json() - kept as opaque JSON text
    # rather than mirrored columns, the same tradeoff `option_items`/
    # `option_availability` deliberately don't make: this shape already
    # has one source of truth (the Pydantic schema) and no query ever
    # filters on an individual field of it, only loads/replaces it whole.
    requirements_json: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

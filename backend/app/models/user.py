from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, false, true
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, BigIntPK


class User(Base):
    """An account, identified solely by its email address - there is no
    password (login is a one-time code sent to `email`, see
    `app/services/auth.py`). Created on first successful login.
    """

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True)
    # Always stored normalized (stripped, lowercased) - see
    # `app.services.auth.normalize_email` - so the plain unique constraint
    # is a case-insensitive one too, on SQLite and Postgres alike.
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=false())
    # False blocks login without deleting the account (and, later, its
    # saved conversations).
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=true())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

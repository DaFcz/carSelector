from datetime import datetime

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, BigIntPK


class LoginCode(Base):
    """One emailed one-time login code. Deliberately keyed by `email`, not
    a `users` FK: the user row is only created once the code is verified
    (first login == signup), so there may be no user yet.
    """

    __tablename__ = "login_codes"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True)
    email: Mapped[str] = mapped_column(String(320), nullable=False, index=True)
    # HMAC-SHA256 hex of the code - never the code itself.
    code_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # Wrong guesses so far; the code is burned once this hits the cap.
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    # Set when the code is used, superseded by a newer request, or burned by
    # too many attempts - any of which makes it unusable.
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Requesting client's IP, only for per-IP rate limiting.
    request_ip: Mapped[str | None] = mapped_column(String(45), nullable=True, index=True)

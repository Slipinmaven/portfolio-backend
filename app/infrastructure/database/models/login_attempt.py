from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base


class LoginAttempt(Base):
    __tablename__ = "login_attempts"

    client_key: Mapped[str] = mapped_column(
        String(64),
        primary_key=True,
    )
    failure_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    window_started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    blocked_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    __table_args__ = (
        Index("ix_login_attempts_updated_at", "updated_at"),
    )

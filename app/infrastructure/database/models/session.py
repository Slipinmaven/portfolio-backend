from datetime import datetime
from typing import TYPE_CHECKING
from sqlalchemy.dialects.postgresql import INET
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    Uuid,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.infrastructure.database.base import Base

if TYPE_CHECKING:
    from app.infrastructure.database.models.user import User
    from app.infrastructure.database.models.trusted_device import TrustedDevice

class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid4,
        nullable=False,
    )
    user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id"),
        nullable=False
    )
    trusted_device_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        nullable=True
    )
    refresh_token_hash: Mapped[str] = mapped_column(
        String(255),
        nullable=False
    )
    ip_address: Mapped[str | None] = mapped_column(
        INET,
        nullable=True
    )
    user_agent: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now()
    )
    last_activity_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now()
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )
    revocation_reason: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True
    )

    #Relationships
    user: Mapped["User"] = relationship(
        "User",
        back_populates="sessions",
        lazy="joined"
    )
    trusted_device: Mapped["TrustedDevice | None"] = relationship(
        "TrustedDevice",
        back_populates="sessions",
        lazy="joined",
        foreign_keys=[trusted_device_id],
    )

    #  PERFORMANCE & INTEGRITY CONFIGURATION
    __table_args__ = (
        ForeignKeyConstraint(
            ["user_id", "trusted_device_id"],
            ["trusted_devices.user_id", "trusted_devices.id"],
            ondelete="SET NULL (trusted_device_id)",
            name="fk_sessions_user_trusted_device",
        ),
        Index(
            "ix_sessions_user_id",
            "user_id",
        ),
        Index(
            "uq_sessions_refresh_token_hash",
            "refresh_token_hash",
            unique=True,
        ),
        Index(
            "ix_sessions_expires_at",
            "expires_at",
        ),
        Index(
            "ix_sessions_unrevoked_user",
            "user_id",
            postgresql_where=text("revoked_at IS NULL"),
        ),
        Index(
            "ix_sessions_trusted_device_id",
            "trusted_device_id",
        ),
        CheckConstraint(
            sqltext="(revoked_at IS NULL AND revocation_reason IS NULL) OR (revoked_at IS NOT NULL AND revocation_reason IS NOT NULL)",
            name="chk_sessions_revocation_integrity"
        ),
        CheckConstraint(
            sqltext="expires_at > created_at",
            name="chk_sessions_expiration_validity"
        )
    )
from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4
from sqlalchemy.dialects.postgresql import INET
from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
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
    from app.infrastructure.database.models.session import Session

class TrustedDevice(Base):
    __tablename__ = "trusted_devices"

    # 1. PRIMARY KEY & RELATIONS
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

    # 2. SECURITY TOKENS & NETWORK DATA
    # (Removed inline unique=True to let the explicit index handle it cleanly)
    device_token_hash: Mapped[str] = mapped_column(
        String(255),
        nullable=False
    )
    ip_address: Mapped[str | None] = mapped_column(
        INET,
        nullable=True
    )

    # 3. DEVICE METADATA / USER AGENT BREAKDOWN
    device_name: Mapped[str | None] = mapped_column(String(150), nullable=True)
    device_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    browser: Mapped[str | None] = mapped_column(String(100), nullable=True)
    operating_system: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # 4. TIMESTAMPS & LIFECYCLE
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now()
    )
    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        server_default=func.now(),
        onupdate=func.now()
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False
    )

    # 5. SOFT-DELETE / REVOCATION AUDITING
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
        back_populates="trusted_devices",
        lazy="joined"
    )
    sessions: Mapped[list["Session"]] = relationship(
        "Session",
        back_populates="trusted_device",
        lazy="selectin",
        foreign_keys="Session.trusted_device_id",
        passive_deletes="all",
    )

    # 6. PERFORMANCE & INTEGRITY CONFIGURATION
    __table_args__ = (
        # Globally enforces unique token hashes securely
        Index(
            "uq_trusted_devices_token_hash",
            "device_token_hash",
            unique=True,
        ),
        Index(
            "uq_trusted_devices_user_id_id",
            "user_id",
            "id",
            unique=True,
        ),
        Index(
            "ix_trusted_devices_user_id",
            "user_id",
        ),
        Index(
            "ix_trusted_devices_expires_at",
            "expires_at",
        ),
        Index(
            "ix_trusted_devices_unrevoked_user",
            "user_id",
            postgresql_where=text("revoked_at IS NULL"),
        ),
        # Ensures that a token cannot be generated pre-expired
        CheckConstraint(
            sqltext="expires_at > created_at",
            name="chk_trusted_devices_expiration_validity"
        ),
        # Guarantees audit trail consistency (Both fields must exist, or both are null)
        CheckConstraint(
            sqltext=(
                "(revoked_at IS NULL AND revocation_reason IS NULL) "
                "OR "
                "(revoked_at IS NOT NULL AND revocation_reason IS NOT NULL)"
            ),
            name="chk_trusted_devices_revocation_integrity"
        )

    )

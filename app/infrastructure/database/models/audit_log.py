from datetime import datetime
from typing import TYPE_CHECKING, Any
from sqlalchemy.dialects.postgresql import JSONB, INET
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Uuid,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.infrastructure.database.base import Base

if TYPE_CHECKING:
    from app.infrastructure.database.models.user import User

class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid4,
        nullable=False,
    )
    user_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )
    action: Mapped[str] = mapped_column(
        String(100),
        nullable=False
    )
    entity_type: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True
    )
    entity_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        nullable=True
    )
    old_values: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True
    )
    new_values: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False
    )
    request_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        nullable=True
    )
    ip_address: Mapped[str | None] = mapped_column(
        INET,
        nullable=True
    )
    user_agent: Mapped[str | None] = mapped_column(
        Text,
        nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now()
    )
    #RELATIONSHIPS
    user: Mapped["User"] = relationship(
        "User",
        back_populates="audit_logs",
        lazy="joined"
    )

    # Performance & Integrity Configuration
    __table_args__ = (
        Index(
            "ix_audit_logs_created_at",
            "created_at",
        ),
        Index(
            "ix_audit_logs_user_created",
            "user_id",
            "created_at",
        ),
        Index(
            "ix_audit_logs_entity_created",
            "entity_type",
            "entity_id",
            "created_at",
        ),
        Index(
            "ix_audit_logs_request_id",
            "request_id",
        ),
        CheckConstraint(
            sqltext="status IN ('success', 'failure')",
            name="check_audit_log_status"
        ),
        CheckConstraint(
            name="ck_audit_logs_entity_pair",
            sqltext="(entity_type IS NULL AND entity_id IS NULL) OR (entity_type IS NOT NULL AND entity_id IS NOT NULL)"
        ),
    )

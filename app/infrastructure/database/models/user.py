from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Index,
    String,
    Uuid,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from app.infrastructure.database.base import Base
from app.infrastructure.database.models.enums import UserRole

if TYPE_CHECKING:
    from app.infrastructure.database.models.trusted_device import TrustedDevice
    from app.infrastructure.database.models.session import Session
    from app.infrastructure.database.models.audit_log import AuditLog

class User(Base):
    __tablename__ = "users"

    @validates("email")
    def normalize_email(self, _key: str, email: str) -> str:
        return email.strip().lower()

    id: Mapped[UUID] = mapped_column( 
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid4,
        nullable=False,
    )
    email: Mapped[str] = mapped_column(
        String(255),
        nullable=False
    )
    password_hash: Mapped[str] = mapped_column(
        String(255),
        nullable=False
    )
    first_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False
    )
    last_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False
    )
    role: Mapped[UserRole] = mapped_column(
        String(20),
        nullable=False,
        default=UserRole.EDITOR.value
    )
    is_active: Mapped[bool] = mapped_column(
        nullable=False,
        default=True,
        server_default="true",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now()
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now()
    )

    last_login_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )

    #Relationships

    trusted_devices: Mapped[list["TrustedDevice"]] = relationship(
        "TrustedDevice",
        back_populates="user",
        lazy="selectin",
        cascade="all, delete-orphan"
    )
    sessions: Mapped[list["Session"]] = relationship(
        "Session",
        back_populates="user",
        lazy="selectin"
    )
    audit_logs: Mapped[list["AuditLog"]] = relationship(
        "AuditLog",
        back_populates="user",
        lazy="selectin"
    )

    __table_args__ = (
        CheckConstraint(
            sqltext=r"email ~* '^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$'",
            name="check_email_format"
        ),
        CheckConstraint(
            sqltext="email = LOWER(email)",
            name="check_email_lowercase"
        ),
        CheckConstraint(
            sqltext="role IN ('admin', 'editor')",
            name="check_user_role",
        ),
        Index(
            "uq_user_email",
            text("lower(email)"),
            unique=True,
        ),
    )

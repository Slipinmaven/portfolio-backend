from datetime import datetime
from uuid import UUID, uuid4
from typing import List, Optional, TYPE_CHECKING
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Index,
    String,
    text,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.infrastructure.database.base import Base

if TYPE_CHECKING:
    from app.infrastructure.database.models.project import Project


class Tag(Base):
    __tablename__ = "tags"

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid4,
        nullable=False,
    )
    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )
    slug: Mapped[str] = mapped_column(
        String(120),
        nullable=False,
        unique=True,
    )
    description: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    projects: Mapped[List["Project"]] = relationship(
        "Project",
        secondary="project_tags",
        back_populates="tags",
    )

    # PERFORMANCE & INTEGRITY CONFIGURATIONS
    __table_args__ = (
        Index(
            "ix_tags_is_active",
            "is_active",
        ),
        Index(
            "uq_tags_name_ci",
            text("lower(btrim(name))"), 
            unique=True,
        ),

        CheckConstraint(
            sqltext="slug ~ '^[a-z0-9]+(-[a-z0-9]+)*$'",
            name="ck_tags_slug_format",
        ),
    )
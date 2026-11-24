from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, Index, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.database.base import Base
from app.infrastructure.database.models.enums import PageStatus

if TYPE_CHECKING:
    from app.infrastructure.database.models.page_media import PageMedia
    from app.infrastructure.database.models.page_revision import PageRevision


class Page(Base):
    __tablename__ = "pages"

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid4,
        nullable=False,
    )
    slug: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    system_key: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
        unique=True,
    )
    status: Mapped[PageStatus] = mapped_column(
        String(20),
        nullable=False,
        default=PageStatus.DRAFT.value,
        server_default=PageStatus.DRAFT.value,
    )
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    archived_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
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

    revisions: Mapped[list["PageRevision"]] = relationship(
        "PageRevision",
        back_populates="page",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="PageRevision.revision_number",
    )
    media_associations: Mapped[list["PageMedia"]] = relationship(
        "PageMedia",
        back_populates="page",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    __table_args__ = (
        Index("ix_pages_status", "status"),
        CheckConstraint(
            "slug ~ '^[a-z0-9]+(-[a-z0-9]+)*$'",
            name="slug_format",
        ),
        CheckConstraint(
            "system_key IS NULL OR system_key IN ('HOME', 'ABOUT', 'CONTACT')",
            name="system_key",
        ),
        CheckConstraint(
            "system_key IS NULL OR slug = lower(system_key)",
            name="system_slug_locked",
        ),
        CheckConstraint(
            "status IN ('DRAFT', 'PUBLISHED', 'ARCHIVED')",
            name="status",
        ),
        CheckConstraint(
            "status <> 'PUBLISHED' OR published_at IS NOT NULL",
            name="published_has_date",
        ),
        CheckConstraint(
            "(status = 'ARCHIVED') = (archived_at IS NOT NULL)",
            name="archived_pair",
        ),
    )

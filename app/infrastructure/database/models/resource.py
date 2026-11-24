from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Index,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.database.base import Base
from app.infrastructure.database.models.enums import ResourceStatus, ResourceType

if TYPE_CHECKING:
    from app.infrastructure.database.models.post_resource import PostResource
    from app.infrastructure.database.models.project_resource import ProjectResource


class Resource(Base):
    __tablename__ = "resources"

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid4,
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    url: Mapped[str] = mapped_column(String(500), nullable=False)
    resource_type: Mapped[ResourceType] = mapped_column(String(20), nullable=False)
    creator: Mapped[str | None] = mapped_column(String(150), nullable=True)
    summary: Mapped[str | None] = mapped_column(String(300), nullable=True)
    commentary: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[ResourceStatus] = mapped_column(
        String(20),
        nullable=False,
        default=ResourceStatus.DRAFT,
        server_default=ResourceStatus.DRAFT.value,
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

    post_associations: Mapped[list["PostResource"]] = relationship(
        "PostResource",
        back_populates="resource",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="PostResource.display_order",
    )
    project_associations: Mapped[list["ProjectResource"]] = relationship(
        "ProjectResource",
        back_populates="resource",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="ProjectResource.display_order",
    )

    __table_args__ = (
        UniqueConstraint("url", name="uq_resources_url"),
        Index(
            "ix_resources_status_type_published",
            "status",
            "resource_type",
            "published_at",
        ),
        CheckConstraint("url ~ '^https://'", name="https_url"),
        CheckConstraint(
            "resource_type IN ('ARTICLE', 'BOOK', 'COURSE', 'DOCS', 'TOOL', "
            "'VIDEO', 'OTHER')",
            name="resource_type",
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

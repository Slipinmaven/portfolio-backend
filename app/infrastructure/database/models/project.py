from datetime import datetime
from typing import TYPE_CHECKING, List
from uuid import UUID, uuid4
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Index,
    Text,
    String,
    Integer,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.infrastructure.database.base import Base
from app.infrastructure.database.models.enums import ProjectStatus, DevelopmentStatus

if TYPE_CHECKING:
    from app.infrastructure.database.models.category import Category
    from app.infrastructure.database.models.project_media import ProjectMedia
    from app.infrastructure.database.models.project_resource import ProjectResource
    from app.infrastructure.database.models.post import Post
    from app.infrastructure.database.models.tag import Tag

class Project(Base):
    __tablename__ = "projects"

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid4,
        nullable=False,
    )
    title: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
    )
    slug: Mapped[str] = mapped_column(
        String(220),
        nullable=False,
        unique=True,
    )
    github_url: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )
    demo_url: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )
    short_description: Mapped[str] = mapped_column(
        String(300),
        nullable=False,
    )
    overview: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    # Type-safe mapping using your application enums saved as raw strings
    status: Mapped[ProjectStatus] = mapped_column(
        String(20),
        nullable=False,
        default=ProjectStatus.DRAFT.value,
        server_default=ProjectStatus.DRAFT.value,
    )
    development_status: Mapped[DevelopmentStatus] = mapped_column(
        String(20),
        nullable=False,
    )
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    archived_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    display_order: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    is_featured: Mapped[bool] = mapped_column(
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

    # RELATIONSHIPS
    categories: Mapped[List["Category"]] = relationship(
        "Category",
        secondary="project_categories",  
        back_populates="projects"
    )
    tags: Mapped[List["Tag"]] = relationship(
        "Tag",
        secondary="project_tags",  
        back_populates="projects"
    )
    media_associations: Mapped[List["ProjectMedia"]] = relationship(
        "ProjectMedia",
        back_populates="project",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    resource_associations: Mapped[List["ProjectResource"]] = relationship(
        "ProjectResource",
        back_populates="project",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="ProjectResource.display_order",
    )
    posts: Mapped[List["Post"]] = relationship(
        "Post",
        secondary="post_projects",
        back_populates="projects",
    )

    # PERFORMANCE & INTEGRITY CONFIGURATIONS

    __table_args__ = (
        Index(
            "ix_projects_status_display_order",
            "status",
            "display_order",
        ),
        Index(
            "ix_projects_is_featured_status",
            "is_featured",
            "status",
        ),
        Index(
            "ix_projects_display_order",
            "display_order",
        ),

        CheckConstraint(
            sqltext="display_order >= 0",
            name="ck_projects_display_order",
        ),
        CheckConstraint(
            sqltext=r"slug ~ '^[a-z0-9]+(-[a-z0-9]+)*$'",
            name="ck_projects_slug_format",
        ),
        CheckConstraint(
            sqltext="status IN ('DRAFT', 'PUBLISHED', 'ARCHIVED')",
            name="ck_projects_status",
        ),
        CheckConstraint(
            sqltext="development_status IN ('PLANNING', 'IN_PROGRESS', 'COMPLETED', 'ON_HOLD', 'CANCELLED')",
            name="ck_projects_dev_status",
        ),
        CheckConstraint(
            sqltext="github_url IS NULL OR github_url ~ '^https?://'",
            name="ck_projects_github_url",
        ),
        CheckConstraint(
            sqltext="demo_url IS NULL OR demo_url ~ '^https?://'",
            name="ck_projects_demo_url",
        ),
        CheckConstraint(
            sqltext="status <> 'PUBLISHED' OR published_at IS NOT NULL",
            name="ck_projects_published_has_date",
        ),
        CheckConstraint(
            sqltext="(status = 'ARCHIVED') = (archived_at IS NOT NULL)",
            name="ck_projects_archived_pair",
        ),
    )

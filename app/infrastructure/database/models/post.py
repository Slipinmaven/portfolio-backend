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
from app.infrastructure.database.models.enums import PostKind, PostStatus

if TYPE_CHECKING:
    from app.infrastructure.database.models.category import Category
    from app.infrastructure.database.models.media import Media
    from app.infrastructure.database.models.post_media import PostMedia
    from app.infrastructure.database.models.post_resource import PostResource
    from app.infrastructure.database.models.project import Project


class Post(Base):
    __tablename__ = "posts"

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid4,
        nullable=False,
    )
    kind: Mapped[PostKind] = mapped_column(String(10), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(220), nullable=False)
    summary: Mapped[str | None] = mapped_column(String(300), nullable=True)
    body: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="",
        server_default="",
    )
    status: Mapped[PostStatus] = mapped_column(
        String(20),
        nullable=False,
        default=PostStatus.DRAFT,
        server_default=PostStatus.DRAFT.value,
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

    categories: Mapped[list["Category"]] = relationship(
        "Category",
        secondary="post_categories",
        back_populates="posts",
    )
    projects: Mapped[list["Project"]] = relationship(
        "Project",
        secondary="post_projects",
        back_populates="posts",
    )
    media_associations: Mapped[list["PostMedia"]] = relationship(
        "PostMedia",
        back_populates="post",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="PostMedia.role, PostMedia.display_order, PostMedia.media_id",
    )
    resource_associations: Mapped[list["PostResource"]] = relationship(
        "PostResource",
        back_populates="post",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="PostResource.display_order",
    )

    __table_args__ = (
        UniqueConstraint("kind", "slug", name="uq_posts_kind_slug"),
        Index(
            "ix_posts_kind_status_published",
            "kind",
            "status",
            "published_at",
        ),
        CheckConstraint(
            "kind IN ('ARTICLE', 'NOTE')",
            name="ck_posts_kind",
        ),
        CheckConstraint(
            r"slug ~ '^[a-z0-9]+(-[a-z0-9]+)*$'",
            name="ck_posts_slug_format",
        ),
        CheckConstraint(
            "status IN ('DRAFT', 'PUBLISHED', 'ARCHIVED')",
            name="ck_posts_status",
        ),
        CheckConstraint(
            "status <> 'PUBLISHED' OR published_at IS NOT NULL",
            name="ck_posts_published_has_date",
        ),
        CheckConstraint(
            "(status = 'ARCHIVED') = (archived_at IS NOT NULL)",
            name="ck_posts_archived_pair",
        ),
    )

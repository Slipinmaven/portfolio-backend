from datetime import datetime
from uuid import UUID, uuid4
from typing import List, Optional, TYPE_CHECKING
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    text,
    Integer,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.infrastructure.database.base import Base

if TYPE_CHECKING:
    from app.infrastructure.database.models.post import Post
    from app.infrastructure.database.models.project import Project

class Category(Base):
    __tablename__ = "categories"

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid4,
        nullable=False,
    )
    parent_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("categories.id", ondelete="RESTRICT"),
        nullable=True,
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
    display_order: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
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

    #RELATIONSHIPS
    parent: Mapped[Optional["Category"]] = relationship(
        "Category",
        remote_side=[id],
        back_populates="children",
    )
    children: Mapped[List["Category"]] = relationship(
        "Category", 
        back_populates="parent",
        order_by="Category.display_order"  # Automatically sorts children by your index order!
    )

    projects: Mapped[List["Project"]] = relationship(
        "Project",
        secondary="project_categories", 
        back_populates="categories"
    )
    posts: Mapped[List["Post"]] = relationship(
        "Post",
        secondary="post_categories",
        back_populates="categories",
    )

    #PERFORMANCE AND INTEGRITY CONFIGURATIONS

    __table_args__ = (
        # Compound index for sorting subcategories
        Index(
            "ix_categories_parent_order",
            "parent_id",
            "display_order",
        ),
        # Index for filtering active categories
        Index(
            "ix_categories_is_active",
            "is_active",
        ),
        # The unique expression constraint with NULLS NOT DISTINCT
        Index(
            "uq_categories_sibling_name",
            "parent_id",
            text("lower(btrim(name))"),
            unique=True,
            postgresql_nulls_not_distinct=True,  # Requires PostgreSQL 15+ & SQLAlchemy 2.0+
        ),
       
        CheckConstraint(
            sqltext=r"slug ~ '^[a-z0-9]+(-[a-z0-9]+)*$'",
            name="ck_categories_slug_format",
        ),
        CheckConstraint(
            sqltext="display_order >= 0",
            name="ck_categories_order",
        ),
        CheckConstraint(
            sqltext="parent_id <> id",
            name="ck_categories_not_own_parent"
        )
    )

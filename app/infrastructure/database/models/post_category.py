from uuid import UUID

from sqlalchemy import ForeignKey, Index, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base


class PostCategory(Base):
    __tablename__ = "post_categories"

    post_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("posts.id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    )
    category_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("categories.id", ondelete="RESTRICT"),
        primary_key=True,
        nullable=False,
    )

    __table_args__ = (
        Index("ix_post_categories_category_id", "category_id"),
    )

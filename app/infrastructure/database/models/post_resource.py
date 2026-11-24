from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.database.base import Base


class PostResource(Base):
    __tablename__ = "post_resources"

    post_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("posts.id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    )
    resource_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("resources.id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    )
    display_order: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )

    post = relationship("Post", back_populates="resource_associations")
    resource = relationship("Resource", back_populates="post_associations")

    __table_args__ = (
        CheckConstraint("display_order >= 0", name="display_order"),
        Index("ix_post_resources_resource_id", "resource_id"),
    )

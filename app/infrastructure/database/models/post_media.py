from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.schema import conv

from app.infrastructure.database.base import Base
from app.infrastructure.database.models.enums import PostMediaRole

if TYPE_CHECKING:
    from app.infrastructure.database.models.media import Media
    from app.infrastructure.database.models.post import Post


class PostMedia(Base):
    __tablename__ = "post_media"

    post_id: Mapped[UUID] = mapped_column(
        ForeignKey("posts.id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    )
    media_id: Mapped[UUID] = mapped_column(
        ForeignKey("media.id", ondelete="RESTRICT"),
        primary_key=True,
        nullable=False,
    )
    role: Mapped[PostMediaRole] = mapped_column(
        String(20),
        primary_key=True,
        nullable=False,
    )
    display_order: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    caption: Mapped[str | None] = mapped_column(String(300), nullable=True)

    post: Mapped["Post"] = relationship(
        "Post",
        back_populates="media_associations",
    )
    media: Mapped["Media"] = relationship(
        "Media",
        back_populates="post_associations",
    )

    __table_args__ = (
        Index("ix_post_media_media_id", "media_id"),
        CheckConstraint(
            "role IN ('INLINE', 'ATTACHMENT')",
            name=conv("ck_post_media_role"),
        ),
        CheckConstraint(
            "display_order >= 0",
            name=conv("ck_post_media_order"),
        ),
    )

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.schema import conv

from app.infrastructure.database.base import Base

if TYPE_CHECKING:
    from app.infrastructure.database.models.media import Media


class MediaLink(Base):
    __tablename__ = "media_links"

    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        default=uuid4,
        nullable=False,
    )
    media_id: Mapped[UUID] = mapped_column(
        ForeignKey("media.id", ondelete="CASCADE"),
        nullable=False,
    )
    url: Mapped[str] = mapped_column(String(500), nullable=False)
    label: Mapped[str | None] = mapped_column(String(100), nullable=True)
    display_order: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    media: Mapped["Media"] = relationship("Media", back_populates="links")

    __table_args__ = (
        Index("uq_media_links_media_url", "media_id", "url", unique=True),
        Index("ix_media_links_media_order", "media_id", "display_order"),
        CheckConstraint(
            "url ~ '^https://'",
            name=conv("ck_media_links_https"),
        ),
        CheckConstraint(
            "display_order >= 0",
            name=conv("ck_media_links_order"),
        ),
    )

from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import ForeignKey, Index, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.database.base import Base

if TYPE_CHECKING:
    from app.infrastructure.database.models.media import Media
    from app.infrastructure.database.models.page import Page


class PageMedia(Base):
    __tablename__ = "page_media"

    page_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("pages.id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    )
    media_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("media.id", ondelete="RESTRICT"),
        primary_key=True,
        nullable=False,
    )

    page: Mapped["Page"] = relationship(
        "Page",
        back_populates="media_associations",
    )
    media: Mapped["Media"] = relationship("Media")

    __table_args__ = (Index("ix_page_media_media_id", "media_id"),)

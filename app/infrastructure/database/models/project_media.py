from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.schema import conv

from app.infrastructure.database.base import Base
from app.infrastructure.database.models.enums import ProjectMediaRole

if TYPE_CHECKING:
    from app.infrastructure.database.models.media import Media
    from app.infrastructure.database.models.project import Project


class ProjectMedia(Base):
    __tablename__ = "project_media"

    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    )
    media_id: Mapped[UUID] = mapped_column(
        ForeignKey("media.id", ondelete="RESTRICT"),
        primary_key=True,
        nullable=False,
    )
    role: Mapped[ProjectMediaRole] = mapped_column(
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

    project: Mapped["Project"] = relationship(
        "Project",
        back_populates="media_associations",
    )
    media: Mapped["Media"] = relationship(
        "Media",
        back_populates="project_associations",
    )

    __table_args__ = (
        Index("ix_project_media_media_id", "media_id"),
        Index(
            "uq_project_media_cover",
            "project_id",
            unique=True,
            postgresql_where=(role == "COVER"),
        ),
        CheckConstraint(
            "role IN ('COVER', 'GALLERY', 'INLINE', 'ATTACHMENT')",
            name=conv("ck_project_media_role"),
        ),
        CheckConstraint(
            "display_order >= 0",
            name=conv("ck_project_media_order"),
        ),
    )

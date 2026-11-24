from uuid import UUID
from sqlalchemy import ForeignKey, Index, Uuid
from sqlalchemy.orm import Mapped, mapped_column
from app.infrastructure.database.base import Base

class ProjectTag(Base):
    __tablename__ = "project_tags"

    project_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    )
    tag_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("tags.id", ondelete="RESTRICT"),
        primary_key=True,
        nullable=False,
    )

    # PERFORMANCE & INTEGRITY CONFIGURATIONS
    __table_args__ = (
        Index(
            "ix_project_tags_tag_id",
            "tag_id",
        ),
    )
from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.database.base import Base


class ProjectResource(Base):
    __tablename__ = "project_resources"

    project_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
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

    project = relationship("Project", back_populates="resource_associations")
    resource = relationship("Resource", back_populates="project_associations")

    __table_args__ = (
        CheckConstraint("display_order >= 0", name="display_order"),
        Index("ix_project_resources_resource_id", "resource_id"),
    )

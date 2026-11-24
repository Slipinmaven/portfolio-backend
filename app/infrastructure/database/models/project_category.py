from uuid import UUID
from sqlalchemy import ForeignKey, Index, Uuid
from sqlalchemy.orm import Mapped, mapped_column
from app.infrastructure.database.base import Base

class ProjectCategory(Base):
    __tablename__ = "project_categories"

    project_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"), 
        primary_key=True,                             
        nullable=False,
    )
    category_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("categories.id", ondelete="RESTRICT"),
        primary_key=True,                                 
        nullable=False,
    )

    # PERFORMANCE & INTEGRITY CONFIGURATIONS
    __table_args__ = (
        # Explicit index for reverse lookups (Categories -> Projects)
        Index(
            "ix_project_categories_category_id",
            "category_id",
        ),
    )

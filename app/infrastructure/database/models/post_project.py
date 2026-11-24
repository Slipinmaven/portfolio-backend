from sqlalchemy import Column, ForeignKey, Index, Table, Uuid

from app.infrastructure.database.base import Base


post_projects = Table(
    "post_projects",
    Base.metadata,
    Column(
        "post_id",
        Uuid(as_uuid=True),
        ForeignKey("posts.id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    ),
    Column(
        "project_id",
        Uuid(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    ),
    Index("ix_post_projects_project_id", "project_id"),
)

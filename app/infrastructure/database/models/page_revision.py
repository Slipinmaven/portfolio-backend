from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.database.base import Base
from app.infrastructure.database.models.enums import PageRevisionState

if TYPE_CHECKING:
    from app.infrastructure.database.models.page import Page


class PageRevision(Base):
    __tablename__ = "page_revisions"

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid4,
        nullable=False,
    )
    page_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("pages.id", ondelete="CASCADE"),
        nullable=False,
    )
    revision_number: Mapped[int] = mapped_column(Integer, nullable=False)
    state: Mapped[PageRevisionState] = mapped_column(String(12), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    summary: Mapped[str | None] = mapped_column(String(300), nullable=True)
    sections: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default=text("'[]'::jsonb"),
    )
    schema_version: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
        default=1,
        server_default="1",
    )
    change_note: Mapped[str | None] = mapped_column(String(300), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    superseded_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    page: Mapped["Page"] = relationship("Page", back_populates="revisions")

    __table_args__ = (
        Index(
            "uq_page_revisions_page_number",
            "page_id",
            "revision_number",
            unique=True,
        ),
        Index(
            "uq_page_revisions_one_draft",
            "page_id",
            unique=True,
            postgresql_where=text("state = 'DRAFT'"),
        ),
        Index(
            "uq_page_revisions_one_published",
            "page_id",
            unique=True,
            postgresql_where=text("state = 'PUBLISHED'"),
        ),
        CheckConstraint("revision_number > 0", name="number_positive"),
        CheckConstraint(
            "state IN ('DRAFT', 'PUBLISHED', 'SUPERSEDED')",
            name="state",
        ),
        CheckConstraint(
            "jsonb_typeof(sections) = 'array'",
            name="sections_array",
        ),
        CheckConstraint(
            "(state = 'DRAFT' AND published_at IS NULL AND superseded_at IS NULL) "
            "OR (state = 'PUBLISHED' AND published_at IS NOT NULL "
            "AND superseded_at IS NULL) "
            "OR (state = 'SUPERSEDED' AND published_at IS NOT NULL "
            "AND superseded_at IS NOT NULL)",
            name="state_dates",
        ),
    )

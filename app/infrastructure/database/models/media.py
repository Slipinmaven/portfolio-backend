from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    CHAR,
    CheckConstraint,
    DateTime,
    Index,
    Integer,
    String,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.schema import conv

from app.infrastructure.database.base import Base
from app.infrastructure.database.models.enums import MediaKind

if TYPE_CHECKING:
    from app.infrastructure.database.models.media_link import MediaLink
    from app.infrastructure.database.models.project_media import ProjectMedia
    from app.infrastructure.database.models.post_media import PostMedia


class Media(Base):
    __tablename__ = "media"

    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        default=uuid4,
        nullable=False,
    )
    kind: Mapped[MediaKind] = mapped_column(String(20), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(500), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    checksum_sha256: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    alt_text: Mapped[str | None] = mapped_column(String(500), nullable=True)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
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

    links: Mapped[list["MediaLink"]] = relationship(
        "MediaLink",
        back_populates="media",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="MediaLink.display_order",
    )
    project_associations: Mapped[list["ProjectMedia"]] = relationship(
        "ProjectMedia",
        back_populates="media",
        passive_deletes="all",
    )
    post_associations: Mapped[list["PostMedia"]] = relationship(
        "PostMedia",
        back_populates="media",
        passive_deletes="all",
    )

    __table_args__ = (
        Index("uq_media_storage_key", "storage_key", unique=True),
        Index("ix_media_checksum", "checksum_sha256"),
        Index("ix_media_kind_created", "kind", "created_at"),
        CheckConstraint(
            "kind IN ('IMAGE', 'DOCUMENT', 'VIDEO')",
            name=conv("ck_media_kind"),
        ),
        CheckConstraint("size_bytes > 0", name=conv("ck_media_size")),
        CheckConstraint(
            "checksum_sha256 ~ '^[0-9a-f]{64}$'",
            name=conv("ck_media_checksum_format"),
        ),
        CheckConstraint(
            "storage_key !~ '^/'",
            name=conv("ck_media_key_relative"),
        ),
        CheckConstraint(
            "(width IS NULL) = (height IS NULL)",
            name=conv("ck_media_dimensions_pair"),
        ),
        CheckConstraint(
            "width IS NULL OR (width > 0 AND height > 0 AND kind IN ('IMAGE', 'VIDEO'))",
            name=conv("ck_media_dimensions_valid"),
        ),
        CheckConstraint(
            "duration_seconds IS NULL OR (duration_seconds > 0 AND kind = 'VIDEO')",
            name=conv("ck_media_duration_valid"),
        ),
    )

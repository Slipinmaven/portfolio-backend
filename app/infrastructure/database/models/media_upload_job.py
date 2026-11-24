from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.schema import conv

from app.infrastructure.database.base import Base


class MediaUploadJob(Base):
    __tablename__ = "media_upload_jobs"

    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        default=uuid4,
        nullable=False,
    )
    actor_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="PROCESSING",
    )
    media_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("media.id", ondelete="CASCADE"),
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

    __table_args__ = (
        CheckConstraint(
            "status IN ('PROCESSING', 'SUCCEEDED', 'FAILED')",
            name=conv("ck_media_upload_job_status"),
        ),
        CheckConstraint(
            "(status = 'SUCCEEDED') = (media_id IS NOT NULL)",
            name=conv("ck_media_upload_job_result"),
        ),
        Index("ix_media_upload_jobs_actor_created", "actor_id", "created_at"),
    )

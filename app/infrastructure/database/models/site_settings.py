from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    SmallInteger,
    String,
    Text,
    Uuid,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base


class SiteSettings(Base):
    __tablename__ = "site_settings"

    id: Mapped[int] = mapped_column(
        SmallInteger,
        primary_key=True,
        default=1,
        server_default="1",
        nullable=False,
    )
    site_name: Mapped[str] = mapped_column(String(100), nullable=False)
    tagline: Mapped[str | None] = mapped_column(String(200), nullable=True)
    owner_name: Mapped[str] = mapped_column(String(100), nullable=False)
    role_title: Mapped[str | None] = mapped_column(String(150), nullable=True)
    owner_bio: Mapped[str | None] = mapped_column(Text, nullable=True)
    location: Mapped[str | None] = mapped_column(String(120), nullable=True)
    availability_note: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
    )
    language_code: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        default="en",
        server_default="en",
    )
    title_template: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        default="{title} | {site_name}",
        server_default="{title} | {site_name}",
    )
    default_description: Mapped[str | None] = mapped_column(
        String(300),
        nullable=True,
    )
    logo_media_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("media.id", ondelete="RESTRICT"),
        nullable=True,
    )
    favicon_media_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("media.id", ondelete="RESTRICT"),
        nullable=True,
    )
    default_social_image_media_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("media.id", ondelete="RESTRICT"),
        nullable=True,
    )
    profile_image_media_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("media.id", ondelete="RESTRICT"),
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
        CheckConstraint("id = 1", name="singleton"),
        CheckConstraint(
            "language_code ~ '^[a-z]{2,3}(-[A-Za-z0-9]{2,8})*$'",
            name="language_code",
        ),
        CheckConstraint(
            "position('{title}' in title_template) > 0",
            name="title_template",
        ),
    )

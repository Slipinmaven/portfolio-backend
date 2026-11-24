from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Integer,
    String,
    Uuid,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base
from app.infrastructure.database.models.enums import SiteLinkPlatform


class SiteLink(Base):
    __tablename__ = "site_links"

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid4,
        nullable=False,
    )
    platform: Mapped[SiteLinkPlatform] = mapped_column(
        String(20),
        nullable=False,
    )
    url: Mapped[str] = mapped_column(String(500), nullable=False)
    label: Mapped[str | None] = mapped_column(String(100), nullable=True)
    display_order: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    __table_args__ = (
        UniqueConstraint("url", name="url"),
        CheckConstraint(
            "platform IN ('GITHUB', 'LINKEDIN', 'X', 'YOUTUBE', 'TIKTOK', "
            "'INSTAGRAM', 'BLUESKY', 'MASTODON', 'EMAIL', 'WHATSAPP', 'OTHER')",
            name="platform",
        ),
        CheckConstraint(
            "((platform = 'EMAIL' AND url ~ '^mailto:[^[:space:]@]+@[^[:space:]@]+$') "
            "OR (platform <> 'EMAIL' AND url ~ '^https://[^[:space:]]+$'))",
            name="url",
        ),
        CheckConstraint("display_order >= 0", name="display_order"),
    )

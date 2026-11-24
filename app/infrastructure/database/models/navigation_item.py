from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base
from app.infrastructure.database.models.enums import NavigationLinkType, NavigationMenu


class NavigationItem(Base):
    __tablename__ = "navigation_items"

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid4,
        nullable=False,
    )
    menu: Mapped[NavigationMenu] = mapped_column(String(10), nullable=False)
    parent_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    label: Mapped[str] = mapped_column(String(80), nullable=False)
    link_type: Mapped[NavigationLinkType] = mapped_column(String(10), nullable=False)
    page_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("pages.id", ondelete="RESTRICT"),
        nullable=True,
    )
    project_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("projects.id", ondelete="RESTRICT"),
        nullable=True,
    )
    post_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("posts.id", ondelete="RESTRICT"),
        nullable=True,
    )
    category_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("categories.id", ondelete="RESTRICT"),
        nullable=True,
    )
    route_key: Mapped[str | None] = mapped_column(String(20), nullable=True)
    custom_target: Mapped[str | None] = mapped_column(String(500), nullable=True)
    content_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    display_order: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    is_visible: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
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
        UniqueConstraint("menu", "id", name="uq_navigation_items_menu_id"),
        ForeignKeyConstraint(
            ["menu", "parent_id"],
            ["navigation_items.menu", "navigation_items.id"],
            ondelete="CASCADE",
            name="fk_navigation_items_parent_menu",
        ),
        Index(
            "ix_navigation_items_menu_parent_order",
            "menu",
            "parent_id",
            "display_order",
        ),
        CheckConstraint("menu IN ('HEADER', 'FOOTER', 'MOBILE')", name="menu"),
        CheckConstraint(
            "link_type IN ('NONE', 'PAGE', 'ROUTE', 'PROJECT', 'POST', 'CATEGORY', "
            "'EXTERNAL', 'EMAIL', 'PHONE', 'TEXT')",
            name="link_type",
        ),
        CheckConstraint(
            "route_key IS NULL OR route_key IN "
            "('PROJECTS', 'ARTICLES', 'NOTES', 'RESOURCES')",
            name="route_key",
        ),
        CheckConstraint(
            "num_nonnulls(page_id, project_id, post_id, category_id, route_key, "
            "custom_target, content_text) = "
            "CASE WHEN link_type = 'NONE' THEN 0 ELSE 1 END",
            name="one_target",
        ),
        CheckConstraint("link_type <> 'PAGE' OR page_id IS NOT NULL", name="page"),
        CheckConstraint(
            "link_type <> 'PROJECT' OR project_id IS NOT NULL",
            name="project",
        ),
        CheckConstraint(
            "link_type <> 'POST' OR post_id IS NOT NULL",
            name="post",
        ),
        CheckConstraint(
            "link_type <> 'CATEGORY' OR category_id IS NOT NULL",
            name="category",
        ),
        CheckConstraint(
            "link_type <> 'ROUTE' OR route_key IS NOT NULL",
            name="route",
        ),
        CheckConstraint(
            "link_type NOT IN ('EXTERNAL', 'EMAIL', 'PHONE', 'TEXT') "
            "OR menu = 'FOOTER'",
            name="footer_content_only",
        ),
        CheckConstraint(
            "custom_target IS NULL OR link_type IN ('EXTERNAL', 'EMAIL', 'PHONE')",
            name="custom_target_type",
        ),
        CheckConstraint(
            "content_text IS NULL OR link_type = 'TEXT'",
            name="content_text_type",
        ),
        CheckConstraint(
            "link_type <> 'EXTERNAL' OR custom_target ~ '^https://[^[:space:]]+$'",
            name="external_target",
        ),
        CheckConstraint(
            "link_type <> 'EMAIL' OR "
            "custom_target ~ '^[^[:space:]@]+@[^[:space:]@]+\\.[^[:space:]@]+$'",
            name="email_target",
        ),
        CheckConstraint(
            "link_type <> 'PHONE' OR "
            "custom_target ~ '^\\+?[0-9][0-9 ().-]{5,24}$'",
            name="phone_target",
        ),
        CheckConstraint(
            "link_type <> 'TEXT' OR "
            "(length(btrim(content_text)) BETWEEN 1 AND 1000)",
            name="text_content",
        ),
        CheckConstraint("display_order >= 0", name="order"),
        CheckConstraint(
            "parent_id IS NULL OR parent_id <> id",
            name="not_own_parent",
        ),
    )

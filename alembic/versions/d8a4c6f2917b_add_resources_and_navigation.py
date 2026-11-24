"""add resources and configurable navigation

Revision ID: d8a4c6f2917b
Revises: f2a9c1d8e047
Create Date: 2026-12-03
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "d8a4c6f2917b"
down_revision: str | Sequence[str] | None = "c84b7d2a9510"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "resources",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("url", sa.String(length=500), nullable=False),
        sa.Column("resource_type", sa.String(length=20), nullable=False),
        sa.Column("creator", sa.String(length=150), nullable=True),
        sa.Column("summary", sa.String(length=300), nullable=True),
        sa.Column("commentary", sa.Text(), nullable=True),
        sa.Column(
            "status",
            sa.String(length=20),
            server_default="DRAFT",
            nullable=False,
        ),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint("url ~ '^https://'", name=op.f("ck_resources_https_url")),
        sa.CheckConstraint(
            "resource_type IN ('ARTICLE', 'BOOK', 'COURSE', 'DOCS', 'TOOL', "
            "'VIDEO', 'OTHER')",
            name=op.f("ck_resources_resource_type"),
        ),
        sa.CheckConstraint(
            "status IN ('DRAFT', 'PUBLISHED', 'ARCHIVED')",
            name=op.f("ck_resources_status"),
        ),
        sa.CheckConstraint(
            "status <> 'PUBLISHED' OR published_at IS NOT NULL",
            name=op.f("ck_resources_published_has_date"),
        ),
        sa.CheckConstraint(
            "(status = 'ARCHIVED') = (archived_at IS NOT NULL)",
            name=op.f("ck_resources_archived_pair"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_resources")),
        sa.UniqueConstraint("url", name=op.f("uq_resources_url")),
    )
    op.create_index(
        "ix_resources_status_type_published",
        "resources",
        ["status", "resource_type", "published_at"],
        unique=False,
    )
    op.create_table(
        "post_resources",
        sa.Column("post_id", sa.Uuid(), nullable=False),
        sa.Column("resource_id", sa.Uuid(), nullable=False),
        sa.Column("display_order", sa.Integer(), server_default="0", nullable=False),
        sa.CheckConstraint(
            "display_order >= 0",
            name=op.f("ck_post_resources_display_order"),
        ),
        sa.ForeignKeyConstraint(
            ["post_id"],
            ["posts.id"],
            name=op.f("fk_post_resources_post_id_posts"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["resource_id"],
            ["resources.id"],
            name=op.f("fk_post_resources_resource_id_resources"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "post_id",
            "resource_id",
            name=op.f("pk_post_resources"),
        ),
    )
    op.create_index(
        "ix_post_resources_resource_id",
        "post_resources",
        ["resource_id"],
        unique=False,
    )
    op.create_table(
        "project_resources",
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("resource_id", sa.Uuid(), nullable=False),
        sa.Column("display_order", sa.Integer(), server_default="0", nullable=False),
        sa.CheckConstraint(
            "display_order >= 0",
            name=op.f("ck_project_resources_display_order"),
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_project_resources_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["resource_id"],
            ["resources.id"],
            name=op.f("fk_project_resources_resource_id_resources"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "project_id",
            "resource_id",
            name=op.f("pk_project_resources"),
        ),
    )
    op.create_index(
        "ix_project_resources_resource_id",
        "project_resources",
        ["resource_id"],
        unique=False,
    )
    op.create_table(
        "navigation_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("menu", sa.String(length=10), nullable=False),
        sa.Column("parent_id", sa.Uuid(), nullable=True),
        sa.Column("label", sa.String(length=80), nullable=False),
        sa.Column("link_type", sa.String(length=10), nullable=False),
        sa.Column("page_id", sa.Uuid(), nullable=True),
        sa.Column("project_id", sa.Uuid(), nullable=True),
        sa.Column("post_id", sa.Uuid(), nullable=True),
        sa.Column("category_id", sa.Uuid(), nullable=True),
        sa.Column("route_key", sa.String(length=20), nullable=True),
        sa.Column("display_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "is_visible",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "menu IN ('HEADER', 'FOOTER', 'MOBILE')",
            name=op.f("ck_navigation_items_menu"),
        ),
        sa.CheckConstraint(
            "link_type IN ('NONE', 'PAGE', 'ROUTE', 'PROJECT', 'POST', 'CATEGORY')",
            name=op.f("ck_navigation_items_link_type"),
        ),
        sa.CheckConstraint(
            "route_key IS NULL OR route_key IN "
            "('PROJECTS', 'ARTICLES', 'NOTES', 'RESOURCES')",
            name=op.f("ck_navigation_items_route_key"),
        ),
        sa.CheckConstraint(
            "num_nonnulls(page_id, project_id, post_id, category_id, route_key) = "
            "CASE WHEN link_type = 'NONE' THEN 0 ELSE 1 END",
            name=op.f("ck_navigation_items_one_target"),
        ),
        sa.CheckConstraint(
            "link_type <> 'PAGE' OR page_id IS NOT NULL",
            name=op.f("ck_navigation_items_page"),
        ),
        sa.CheckConstraint(
            "link_type <> 'PROJECT' OR project_id IS NOT NULL",
            name=op.f("ck_navigation_items_project"),
        ),
        sa.CheckConstraint(
            "link_type <> 'POST' OR post_id IS NOT NULL",
            name=op.f("ck_navigation_items_post"),
        ),
        sa.CheckConstraint(
            "link_type <> 'CATEGORY' OR category_id IS NOT NULL",
            name=op.f("ck_navigation_items_category"),
        ),
        sa.CheckConstraint(
            "link_type <> 'ROUTE' OR route_key IS NOT NULL",
            name=op.f("ck_navigation_items_route"),
        ),
        sa.CheckConstraint(
            "display_order >= 0",
            name=op.f("ck_navigation_items_order"),
        ),
        sa.CheckConstraint(
            "parent_id IS NULL OR parent_id <> id",
            name=op.f("ck_navigation_items_not_own_parent"),
        ),
        sa.ForeignKeyConstraint(
            ["category_id"],
            ["categories.id"],
            name=op.f("fk_navigation_items_category_id_categories"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["page_id"],
            ["pages.id"],
            name=op.f("fk_navigation_items_page_id_pages"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["post_id"],
            ["posts.id"],
            name=op.f("fk_navigation_items_post_id_posts"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_navigation_items_project_id_projects"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["menu", "parent_id"],
            ["navigation_items.menu", "navigation_items.id"],
            name=op.f("fk_navigation_items_parent_menu"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_navigation_items")),
        sa.UniqueConstraint(
            "menu",
            "id",
            name=op.f("uq_navigation_items_menu_id"),
        ),
    )
    op.create_index(
        "ix_navigation_items_menu_parent_order",
        "navigation_items",
        ["menu", "parent_id", "display_order"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_navigation_items_menu_parent_order",
        table_name="navigation_items",
    )
    op.drop_table("navigation_items")
    op.drop_index(
        "ix_project_resources_resource_id",
        table_name="project_resources",
    )
    op.drop_table("project_resources")
    op.drop_index(
        "ix_post_resources_resource_id",
        table_name="post_resources",
    )
    op.drop_table("post_resources")
    op.drop_index(
        "ix_resources_status_type_published",
        table_name="resources",
    )
    op.drop_table("resources")

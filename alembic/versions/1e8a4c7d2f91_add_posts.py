"""add posts and post categories

Revision ID: 1e8a4c7d2f91
Revises: c51e7b9f4a20
Create Date: 2026-11-19 11:41:00.000000
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "1e8a4c7d2f91"
down_revision: str | Sequence[str] | None = "c51e7b9f4a20"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "posts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=10), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("slug", sa.String(length=220), nullable=False),
        sa.Column("summary", sa.String(length=300), nullable=True),
        sa.Column("body", sa.Text(), server_default="", nullable=False),
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
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "kind IN ('ARTICLE', 'NOTE')",
            name=op.f("ck_posts_ck_posts_kind"),
        ),
        sa.CheckConstraint(
            "slug ~ '^[a-z0-9]+(-[a-z0-9]+)*$'",
            name=op.f("ck_posts_ck_posts_slug_format"),
        ),
        sa.CheckConstraint(
            "status IN ('DRAFT', 'PUBLISHED', 'ARCHIVED')",
            name=op.f("ck_posts_ck_posts_status"),
        ),
        sa.CheckConstraint(
            "status <> 'PUBLISHED' OR published_at IS NOT NULL",
            name=op.f("ck_posts_ck_posts_published_has_date"),
        ),
        sa.CheckConstraint(
            "(status = 'ARCHIVED') = (archived_at IS NOT NULL)",
            name=op.f("ck_posts_ck_posts_archived_pair"),
        ),
        sa.PrimaryKeyConstraint("id", name="pk_posts"),
        sa.UniqueConstraint("kind", "slug", name="uq_posts_kind_slug"),
    )
    op.create_index(
        "ix_posts_kind_status_published",
        "posts",
        ["kind", "status", "published_at"],
        unique=False,
    )
    op.create_table(
        "post_categories",
        sa.Column("post_id", sa.Uuid(), nullable=False),
        sa.Column("category_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["category_id"],
            ["categories.id"],
            name="fk_post_categories_category_id_categories",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["post_id"],
            ["posts.id"],
            name="fk_post_categories_post_id_posts",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "post_id",
            "category_id",
            name="pk_post_categories",
        ),
    )
    op.create_index(
        "ix_post_categories_category_id",
        "post_categories",
        ["category_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_post_categories_category_id", table_name="post_categories")
    op.drop_table("post_categories")
    op.drop_index("ix_posts_kind_status_published", table_name="posts")
    op.drop_table("posts")

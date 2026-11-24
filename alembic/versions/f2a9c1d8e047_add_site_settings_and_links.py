"""add site settings and social links

Revision ID: f2a9c1d8e047
Revises: d71c90e4a5b2
Create Date: 2026-11-21
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "f2a9c1d8e047"
down_revision: str | Sequence[str] | None = "d71c90e4a5b2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "site_settings",
        sa.Column("id", sa.SmallInteger(), server_default="1", nullable=False),
        sa.Column("site_name", sa.String(length=100), nullable=False),
        sa.Column("tagline", sa.String(length=200), nullable=True),
        sa.Column("owner_name", sa.String(length=100), nullable=False),
        sa.Column("role_title", sa.String(length=150), nullable=True),
        sa.Column("owner_bio", sa.Text(), nullable=True),
        sa.Column("location", sa.String(length=120), nullable=True),
        sa.Column("availability_note", sa.String(length=200), nullable=True),
        sa.Column(
            "language_code",
            sa.String(length=10),
            server_default="en",
            nullable=False,
        ),
        sa.Column(
            "title_template",
            sa.String(length=100),
            server_default="{title} | {site_name}",
            nullable=False,
        ),
        sa.Column("default_description", sa.String(length=300), nullable=True),
        sa.Column("logo_media_id", sa.Uuid(), nullable=True),
        sa.Column("favicon_media_id", sa.Uuid(), nullable=True),
        sa.Column("default_social_image_media_id", sa.Uuid(), nullable=True),
        sa.Column("profile_image_media_id", sa.Uuid(), nullable=True),
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
        sa.CheckConstraint("id = 1", name=op.f("ck_site_settings_singleton")),
        sa.CheckConstraint(
            "language_code ~ '^[a-z]{2,3}(-[A-Za-z0-9]{2,8})*$'",
            name=op.f("ck_site_settings_language_code"),
        ),
        sa.CheckConstraint(
            "position('{title}' in title_template) > 0",
            name=op.f("ck_site_settings_title_template"),
        ),
        sa.ForeignKeyConstraint(
            ["logo_media_id"],
            ["media.id"],
            name=op.f("fk_site_settings_logo_media_id_media"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["favicon_media_id"],
            ["media.id"],
            name=op.f("fk_site_settings_favicon_media_id_media"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["default_social_image_media_id"],
            ["media.id"],
            name=op.f("fk_site_settings_default_social_image_media_id_media"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["profile_image_media_id"],
            ["media.id"],
            name=op.f("fk_site_settings_profile_image_media_id_media"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_site_settings")),
    )
    op.create_table(
        "site_links",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("platform", sa.String(length=20), nullable=False),
        sa.Column("url", sa.String(length=500), nullable=False),
        sa.Column("label", sa.String(length=100), nullable=True),
        sa.Column(
            "display_order",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "platform IN ('GITHUB', 'LINKEDIN', 'X', 'YOUTUBE', 'TIKTOK', "
            "'INSTAGRAM', 'BLUESKY', 'MASTODON', 'EMAIL', 'OTHER')",
            name=op.f("ck_site_links_platform"),
        ),
        sa.CheckConstraint(
            "((platform = 'EMAIL' AND url ~ '^mailto:[^[:space:]@]+@[^[:space:]@]+$') "
            "OR (platform <> 'EMAIL' AND url ~ '^https://[^[:space:]]+$'))",
            name=op.f("ck_site_links_url"),
        ),
        sa.CheckConstraint(
            "display_order >= 0",
            name=op.f("ck_site_links_display_order"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_site_links")),
        sa.UniqueConstraint("url", name=op.f("uq_site_links_url")),
    )
    op.bulk_insert(
        sa.table(
            "site_settings",
            sa.column("id", sa.SmallInteger()),
            sa.column("site_name", sa.String()),
            sa.column("tagline", sa.String()),
            sa.column("owner_name", sa.String()),
            sa.column("role_title", sa.String()),
            sa.column("owner_bio", sa.Text()),
            sa.column("language_code", sa.String()),
            sa.column("title_template", sa.String()),
            sa.column("default_description", sa.String()),
        ),
        [
            {
                "id": 1,
                "site_name": "Portfolio",
                "tagline": "Work / words / ideas",
                "owner_name": "Jasper Mbugua Ngigi",
                "role_title": "Full Stack Developer",
                "owner_bio": "I build useful software for real-world problems.",
                "language_code": "en",
                "title_template": "{title} | {site_name}",
                "default_description": (
                    "Projects, writing, and ideas by Jasper Mbugua Ngigi."
                ),
            }
        ],
    )


def downgrade() -> None:
    op.drop_table("site_links")
    op.drop_table("site_settings")

"""add post media and project associations

Revision ID: 8b3c2d7f4a19
Revises: 1e8a4c7d2f91
Create Date: 2026-11-19 13:15:00.000000
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "8b3c2d7f4a19"
down_revision: str | Sequence[str] | None = "1e8a4c7d2f91"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "post_media",
        sa.Column("post_id", sa.Uuid(), nullable=False),
        sa.Column("media_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("display_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("caption", sa.String(length=300), nullable=True),
        sa.CheckConstraint(
            "role IN ('INLINE', 'ATTACHMENT')",
            name=op.f("ck_post_media_role"),
        ),
        sa.CheckConstraint(
            "display_order >= 0",
            name=op.f("ck_post_media_order"),
        ),
        sa.ForeignKeyConstraint(
            ["media_id"],
            ["media.id"],
            name="fk_post_media_media_id_media",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["post_id"],
            ["posts.id"],
            name="fk_post_media_post_id_posts",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "post_id",
            "media_id",
            "role",
            name="pk_post_media",
        ),
    )
    op.create_index(
        "ix_post_media_media_id",
        "post_media",
        ["media_id"],
        unique=False,
    )
    op.create_table(
        "post_projects",
        sa.Column("post_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["post_id"],
            ["posts.id"],
            name="fk_post_projects_post_id_posts",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name="fk_post_projects_project_id_projects",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "post_id",
            "project_id",
            name="pk_post_projects",
        ),
    )
    op.create_index(
        "ix_post_projects_project_id",
        "post_projects",
        ["project_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_post_projects_project_id", table_name="post_projects")
    op.drop_table("post_projects")
    op.drop_index("ix_post_media_media_id", table_name="post_media")
    op.drop_table("post_media")

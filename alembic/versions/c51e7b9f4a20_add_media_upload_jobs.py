"""add persistent media upload jobs

Revision ID: c51e7b9f4a20
Revises: 5908702d9b0c
Create Date: 2026-11-19
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "c51e7b9f4a20"
down_revision: str | Sequence[str] | None = "a31d9f4b6c82"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "media_upload_jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("media_id", sa.Uuid(), nullable=True),
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
            "status IN ('PROCESSING', 'SUCCEEDED', 'FAILED')",
            name=op.f("ck_media_upload_job_status"),
        ),
        sa.CheckConstraint(
            "(status = 'SUCCEEDED') = (media_id IS NOT NULL)",
            name=op.f("ck_media_upload_job_result"),
        ),
        sa.ForeignKeyConstraint(
            ["actor_id"],
            ["users.id"],
            name=op.f("fk_media_upload_jobs_actor_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["media_id"],
            ["media.id"],
            name=op.f("fk_media_upload_jobs_media_id_media"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_media_upload_jobs")),
    )
    op.create_index(
        "ix_media_upload_jobs_actor_created",
        "media_upload_jobs",
        ["actor_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_media_upload_jobs_actor_created",
        table_name="media_upload_jobs",
    )
    op.drop_table("media_upload_jobs")

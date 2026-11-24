"""add persistent login rate-limit state

Revision ID: b6d2f3a1c901
Revises: 9c4a31d2b7e0
Create Date: 2026-11-04
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "b6d2f3a1c901"
down_revision: str | Sequence[str] | None = "9c4a31d2b7e0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "login_attempts",
        sa.Column("client_key", sa.String(length=64), nullable=False),
        sa.Column("failure_count", sa.Integer(), nullable=False),
        sa.Column("window_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("blocked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("client_key", name=op.f("pk_login_attempts")),
    )
    op.create_index(
        "ix_login_attempts_updated_at",
        "login_attempts",
        ["updated_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_login_attempts_updated_at", table_name="login_attempts")
    op.drop_table("login_attempts")

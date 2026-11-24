"""add authentication foreign keys

Revision ID: 9c4a31d2b7e0
Revises: 625cc770b5cd
Create Date: 2026-11-03
"""

from collections.abc import Sequence

from alembic import op


revision: str = "9c4a31d2b7e0"
down_revision: str | Sequence[str] | None = "625cc770b5cd"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_foreign_key(
        op.f("fk_audit_logs_user_id_users"),
        "audit_logs",
        "users",
        ["user_id"],
        ["id"],
    )
    op.create_foreign_key(
        op.f("fk_sessions_user_id_users"),
        "sessions",
        "users",
        ["user_id"],
        ["id"],
    )
    op.create_foreign_key(
        op.f("fk_sessions_trusted_device_id_trusted_devices"),
        "sessions",
        "trusted_devices",
        ["trusted_device_id"],
        ["id"],
    )
    op.create_foreign_key(
        op.f("fk_trusted_devices_user_id_users"),
        "trusted_devices",
        "users",
        ["user_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("fk_trusted_devices_user_id_users"),
        "trusted_devices",
        type_="foreignkey",
    )
    op.drop_constraint(
        op.f("fk_sessions_trusted_device_id_trusted_devices"),
        "sessions",
        type_="foreignkey",
    )
    op.drop_constraint(
        op.f("fk_sessions_user_id_users"),
        "sessions",
        type_="foreignkey",
    )
    op.drop_constraint(
        op.f("fk_audit_logs_user_id_users"),
        "audit_logs",
        type_="foreignkey",
    )
